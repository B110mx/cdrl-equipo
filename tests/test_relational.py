"""M02: pruebas PostgreSQL aisladas; nunca borran tablas del esquema público."""
import json
import os
import subprocess
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from psycopg2 import errors, sql

from scripts.migrate import apply_migrations
from src.db import DatabaseConnection
from src.relational import (
    devices_by_status, measurements_by_device, metric_summary, seed_database,
)

ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 9, 3, tzinfo=timezone.utc)
END = START + timedelta(days=1)
SCHEMAS = {"created": 0, "removed": 0}


class IsolatedDatabase(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseConnection()
        self.conn = self.db.connect()
        self.addCleanup(self.db.close)
        self.schema = "m02_test_" + uuid.uuid4().hex
        with self.conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.commit()
        SCHEMAS["created"] += 1
        self.addCleanup(self.cleanup_schema)
        self.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        self.conn.commit()

    def execute(self, query, parameters=None):
        with self.conn.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchall() if cursor.description else None

    def cleanup_schema(self):
        self.conn.rollback()
        self.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.conn.commit()
        self.assertEqual(self.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname=%s", (self.schema,)), [])
        SCHEMAS["removed"] += 1

    def snapshot(self):
        return (
            self.execute("SELECT * FROM devices ORDER BY device_id"),
            self.execute("SELECT * FROM telemetry_measurements ORDER BY event_id"),
        )

    def insert(self, device="sensor-lab-01", value=23.75, metric="temperature", unit="celsius"):
        self.execute("""INSERT INTO telemetry_measurements
            (event_id,device_id,recorded_at,metric,value,unit)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (str(uuid.uuid4()), device, START, metric, value, unit))


class TestRelational(IsolatedDatabase):
    def setUp(self):
        super().setUp()
        apply_migrations(self.conn)
        seed_database(self.conn)

    def test_normal_queries(self):
        rows = measurements_by_device(self.conn, "sensor-lab-01", START, END)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["value"], Decimal("23.75"))
        summary = metric_summary(self.conn, "sensor-lab-01", START, END)
        self.assertEqual(len(summary), 2)
        temperature = next(row for row in summary if row["metric"] == "temperature")
        self.assertEqual(temperature["measurement_count"], 1)
        for field in ("minimum", "maximum", "average"):
            self.assertEqual(temperature[field], Decimal("23.75"))
        self.assertEqual([row["measurement_count"] for row in
                          devices_by_status(self.conn, "active")], [2, 1])

    def test_empty_queries(self):
        for device in ("unknown-device", "sensor-lab-03"):
            self.assertEqual(measurements_by_device(self.conn, device, START, END), [])
            self.assertEqual(metric_summary(self.conn, device, START, END), [])
        self.assertEqual(measurements_by_device(
            self.conn, "sensor-lab-01", END, END + timedelta(days=1)), [])
        rows = devices_by_status(self.conn, "inactive")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["measurement_count"], 0)

    def test_limits_date_interval(self):
        boundary = datetime(2026, 9, 3, 17, 59, 30, tzinfo=timezone.utc)
        self.assertEqual(len(measurements_by_device(
            self.conn, "sensor-lab-01", boundary, boundary + timedelta(microseconds=1))), 1)
        self.assertEqual(measurements_by_device(
            self.conn, "sensor-lab-01", START, boundary), [])

    def test_limits_row_count(self):
        for limit, count in ((1, 1), (1000, 2)):
            self.assertEqual(len(measurements_by_device(
                self.conn, "sensor-lab-01", START, END, limit)), count)
        for limit in (0, 1001, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                measurements_by_device(self.conn, "sensor-lab-01", START, END, limit)

    def test_limits_invalid_parameters(self):
        for start, end in ((START, START), (END, START), (START.replace(tzinfo=None), END)):
            for query in (measurements_by_device, metric_summary):
                with self.subTest(query=query.__name__), self.assertRaises(ValueError):
                    query(self.conn, "sensor-lab-01", start, end)
        with self.assertRaises(ValueError):
            devices_by_status(self.conn, "invalid")

    def test_limits_metric_ranges(self):
        for metric, unit, minimum, maximum in (
            ("temperature", "celsius", -80, 200),
            ("humidity", "percent", 0, 100),
            ("battery_voltage", "volt", 0, 1000),
        ):
            for value in (minimum, maximum):
                self.insert(value=value, metric=metric, unit=unit)
            self.conn.rollback()
            for value in (minimum - 1, maximum + 1):
                with self.subTest(metric=metric, value=value):
                    with self.assertRaises(errors.CheckViolation):
                        self.insert(value=value, metric=metric, unit=unit)
                    self.conn.rollback()

    def test_declared_failure_unknown_device(self):
        before = self.snapshot()
        with self.assertRaises(errors.ForeignKeyViolation) as raised:
            self.insert(device="nonexistent-device")
        self.assertEqual(raised.exception.pgcode, "23503")
        self.assertEqual(raised.exception.diag.constraint_name,
                         "telemetry_measurements_device_fk")
        self.conn.rollback()
        self.assertEqual(self.snapshot(), before)

    def test_constraints_devices(self):
        for device, name, status in (
            ("invalid:id", "Synthetic", "active"),
            ("", "Synthetic", "active"),
            ("valid-id", "   ", "active"),
            ("valid-id", "Synthetic", "unknown"),
        ):
            with self.subTest(device=device, status=status):
                with self.assertRaises(errors.CheckViolation):
                    self.execute("INSERT INTO devices(device_id,device_name,status) VALUES (%s,%s,%s)",
                                 (device, name, status))
                self.conn.rollback()
        with self.assertRaises(errors.NotNullViolation):
            self.execute("INSERT INTO devices(device_id,device_name) VALUES (%s,%s)", ("valid-id", None))
        self.conn.rollback()
        with self.assertRaises(errors.UniqueViolation):
            self.execute("INSERT INTO devices(device_id,device_name) VALUES (%s,%s)", ("sensor-lab-01", "Duplicate"))
        self.conn.rollback()

    def test_constraints_referential_actions(self):
        with self.assertRaises(errors.ForeignKeyViolation):
            self.execute("DELETE FROM devices WHERE device_id=%s", ("sensor-lab-01",))
        self.conn.rollback()
        self.execute("UPDATE devices SET device_id=%s WHERE device_id=%s", ("renamed-device", "sensor-lab-01"))
        self.assertEqual(len(measurements_by_device(self.conn, "renamed-device", START, END)), 2)
        self.assertEqual(measurements_by_device(self.conn, "sensor-lab-01", START, END), [])

    def test_constraints_wrong_unit(self):
        with self.assertRaises(errors.CheckViolation):
            self.insert(unit="fahrenheit")

    def test_reproducibility_migrations_seed(self):
        # Conserva también registros adicionales y nombres/estados ya existentes.
        self.execute("INSERT INTO devices(device_id,device_name) VALUES (%s,%s)", ("extra-device", "Synthetic extra"))
        self.insert(device="extra-device")
        self.execute("UPDATE devices SET device_name=%s,status=%s WHERE device_id=%s",
                     ("Custom synthetic name", "inactive", "sensor-lab-02"))
        self.conn.commit()
        before = self.snapshot()
        apply_migrations(self.conn)
        seed_database(self.conn)
        self.assertEqual(self.snapshot(), before)

    def test_parameterization_injection_is_data(self):
        attack = "sensor-lab-01' OR 1=1; DROP TABLE devices; --"
        self.assertEqual(measurements_by_device(self.conn, attack, START, END), [])
        self.assertEqual(metric_summary(self.conn, attack, START, END), [])
        self.assertEqual(self.execute("SELECT count(*) FROM devices"), [(3,)])

    def test_constraints_indexes(self):
        names = {row[0] for row in self.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname=%s", (self.schema,))}
        self.assertTrue({"devices_status_idx", "telemetry_device_time_idx"} <= names)

    def test_constraints_sql_examples(self):
        self.execute((ROOT / "artifacts/test_cases.sql").read_text(encoding="utf-8"))

    def test_runtime_cli_json(self):
        env = dict(os.environ, PGOPTIONS="-c search_path=" + self.schema)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_m02.py"), "--no-artifact"],
            env=env, cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(len(payload["measurements"]), 2)
        self.assertEqual(payload["measurements"][0]["value"], "23.75")
        self.assertEqual(payload["measurements"][0]["recorded_at"], "2026-09-03T17:59:30Z")


class TestUpgrade(IsolatedDatabase):
    def test_reproducibility_upgrade_m01(self):
        self.execute((ROOT / "db/migrations/001_telemetry.sql").read_text(encoding="utf-8"))
        self.execute((ROOT / "db/seed/001_telemetry_seed.sql").read_text(encoding="utf-8"))
        self.conn.commit()
        before = self.execute("SELECT * FROM telemetry_measurements ORDER BY event_id")
        apply_migrations(self.conn)
        self.assertEqual(self.execute("SELECT * FROM telemetry_measurements ORDER BY event_id"), before)
        self.assertEqual(self.execute("SELECT count(*) FROM devices"), [(2,)])
        seed_database(self.conn)
        self.assertEqual(self.execute("SELECT * FROM telemetry_measurements ORDER BY event_id"), before)


if __name__ == "__main__":
    unittest.main()
