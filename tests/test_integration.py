
"""Pruebas de integración reales contra PostgreSQL."""
import unittest
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.db import DatabaseConnection
from src.telemetry import TelemetryManager


def _db_available():
    """Comprueba si se puede conectar a PostgreSQL."""
    db = DatabaseConnection()
    try:
        conn = db.connect()
        db.close()
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()

@unittest.skipUnless(DB_AVAILABLE, "PostgreSQL no disponible; se omiten pruebas de integración")
class TestTelemetryIntegration(unittest.TestCase):
    """Pruebas de integración con base de datos real."""

    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseConnection()
        cls.conn = cls.db.connect()
        cls.cursor = cls.db.get_cursor()
        cls.manager = TelemetryManager(cls.db)

        # Ejecutar migración
        migration_file = Path("db/migrations/001_telemetry.sql")
        sql = migration_file.read_text()
        cls.cursor.execute(sql)
        cls.conn.commit()

        # Ejecutar seed dos veces para probar idempotencia
        seed_file = Path("db/seed/001_telemetry_seed.sql")
        seed_sql = seed_file.read_text()
        cls.cursor.execute(seed_sql)
        cls.conn.commit()
        cls.cursor.execute(seed_sql)
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls.cursor.close()
        cls.db.close()

    def test_01_seed_data_exists(self):
        """El seed insertó al menos un registro."""
        self.cursor.execute("SELECT COUNT(*) FROM telemetry_measurements;")
        count = self.cursor.fetchone()[0]
        self.assertGreater(count, 0)

    def test_02_insert_real_measurement(self):
        """Inserción real usando TelemetryManager y verificación."""
        event_id = str(uuid.uuid4())
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
        event_id = str(uuid.uuid4())
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


if __name__ == '__main__':
    unittest.main()
