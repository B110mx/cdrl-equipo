
"""Pruebas de integración reales contra PostgreSQL."""
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from psycopg2 import sql
import psycopg2

from src.db import DatabaseConnection
from src.telemetry import TelemetryManager


class TestTelemetryIntegration(unittest.TestCase):
    """Pruebas de integración con base de datos real."""

    evidence = {"status": "failed"}

    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseConnection()
        cls.conn = cls.db.connect()
        cls.addClassCleanup(cls.db.close)
        cls.cursor = cls.db.get_cursor()
        cls.addClassCleanup(cls.cursor.close)
        cls.schema = "m01_test_" + uuid.uuid4().hex
        cls.cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        cls.conn.commit()
        cls.addClassCleanup(cls.cleanup_schema)
        cls.cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
        cls.manager = TelemetryManager(cls.db)
        root = Path(__file__).resolve().parents[1]

        # Repeat migration on the same isolated schema.
        migration = (root / "db/migrations/001_telemetry.sql").read_text(encoding="utf-8")
        for _ in range(2):
            cls.cursor.execute(migration)
            cls.conn.commit()

        seed_sql = (root / "db/seed/001_telemetry_seed.sql").read_text(encoding="utf-8")
        snapshots = []
        for _ in range(2):
            cls.cursor.execute(seed_sql)
            cls.conn.commit()
            cls.cursor.execute("SELECT * FROM telemetry_measurements ORDER BY event_id")
            snapshots.append(cls.cursor.fetchall())
        if len(snapshots[0]) != 3 or snapshots[0] != snapshots[1]:
            raise AssertionError("Seed must preserve exactly the same three rows")
        cls.evidence = {
            "status": "passed", "migration_runs": 2, "seed_runs": 2,
            "stable_row_count": 3, "identical_seed_rows": True,
            "temporary_schema_removed": False,
        }

    @classmethod
    def cleanup_schema(cls):
        # Only drop the unique schema created by this test run.
        cls.conn.rollback()
        cls.cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))
        cls.conn.commit()
        cls.cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (cls.schema,))
        if cls.cursor.fetchone() is not None:
            raise AssertionError("Temporary test schema was not removed")
        cls.evidence["temporary_schema_removed"] = True

    def setUp(self):
        self.event_ids = []
        self.addCleanup(self.cleanup_measurements)

    def cleanup_measurements(self):
        self.conn.rollback()
        for event_id in self.event_ids:
            self.cursor.execute("DELETE FROM telemetry_measurements WHERE event_id = %s", (event_id,))
        self.conn.commit()

    def new_event_id(self):
        event_id = str(uuid.uuid4())
        self.event_ids.append(event_id)
        return event_id

    def test_01_seed_data_exists(self):
        """El seed conserva exactamente tres registros."""
        self.cursor.execute("SELECT COUNT(*) FROM telemetry_measurements;")
        count = self.cursor.fetchone()[0]
        self.assertEqual(count, 3)

    def test_02_insert_real_measurement(self):
        """Inserción real usando TelemetryManager y verificación."""
        event_id = self.new_event_id()
        device_id = "sensor-real-001"
        recorded_at = datetime.now(timezone.utc)
        metric = "temperature"
        value = 42.5
        unit = "celsius"
        metadata = {"test": True, "source": "integration"}

        self.manager.insert_measurement(
            event_id=event_id,
            device_id=device_id,
            recorded_at=recorded_at,
            metric=metric,
            value=value,
            unit=unit,
            metadata=metadata
        )

        # Verificar que se insertó correctamente
        self.cursor.execute(
            "SELECT metric, value, unit, metadata FROM telemetry_measurements WHERE event_id = %s",
            (event_id,)
        )
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], metric)
        self.assertEqual(row[1], value)
        self.assertEqual(row[2], unit)
        self.assertEqual(row[3], {"test": True, "source": "integration"})

    def test_03_battery_voltage_max(self):
        """Inserción con battery_voltage en su límite máximo (1000)."""
        event_id = self.new_event_id()
        self.manager.insert_measurement(
            event_id=event_id,
            device_id="battery-001",
            recorded_at=datetime.now(timezone.utc),
            metric="battery_voltage",
            value=1000.0,
            unit="volt",
            metadata={}
        )
        self.cursor.execute("SELECT value FROM telemetry_measurements WHERE event_id = %s", (event_id,))
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1000.0)

    def test_04_database_rejects_invalid_data(self):
        """Check SQL constraints directly, bypassing Python validation."""
        for event_id, device_id, metric, value, unit in (
            ("", "sensor-01", "temperature", 23.75, "celsius"),
            (str(uuid.uuid4()), "sensor:01", "temperature", 23.75, "celsius"),
            (str(uuid.uuid4()), "sensor-01", "humidity", 101, "percent"),
            (str(uuid.uuid4()), "sensor-01", "temperature", 23.75, "fahrenheit"),
        ):
            with self.subTest(metric=metric, unit=unit, device=device_id):
                try:
                    with self.assertRaises(psycopg2.Error):
                        self.cursor.execute(
                            "INSERT INTO telemetry_measurements "
                            "(event_id,device_id,recorded_at,metric,value,unit) "
                            "VALUES (%s,%s,CURRENT_TIMESTAMP,%s,%s,%s)",
                            (event_id, device_id, metric, value, unit),
                        )
                finally:
                    self.conn.rollback()

    def test_05_index_exists(self):
        self.cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname=%s "
            "AND indexname='telemetry_device_time_idx'", (self.schema,)
        )
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertIn("(device_id, recorded_at DESC)", row[0])


if __name__ == '__main__':
    unittest.main()
