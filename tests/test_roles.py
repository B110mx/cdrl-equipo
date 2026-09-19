"""Pruebas de permisos mínimos para los roles PostgreSQL del equipo."""
import unittest
import uuid

from psycopg2 import errors, sql

from scripts.migrate import apply_migrations
from src.db import DatabaseConnection


class TestRolePermissions(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseConnection()
        self.conn = self.db.connect()
        self.schema = "roles_test_" + uuid.uuid4().hex
        self.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.commit()
        self.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        self.conn.commit()
        apply_migrations(self.conn)
        self.execute("INSERT INTO devices(device_id, device_name) VALUES ('role-device', 'Role device')")
        self.conn.commit()

    def tearDown(self):
        self.conn.rollback()
        self.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.conn.commit()
        self.db.close()

    def execute(self, query, parameters=None):
        with self.conn.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchall() if cursor.description else None

    def assume_role(self, role):
        self.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))

    def reset_role(self):
        self.conn.rollback()
        self.execute("RESET ROLE")
        self.conn.commit()

    def test_declared_permissions_are_available(self):
        self.assume_role("cdrl_reader")
        self.assertEqual(self.execute("SELECT count(*) FROM devices"), [(1,)])
        self.reset_role()

        self.assume_role("cdrl_writer")
        self.execute("INSERT INTO telemetry_measurements "
                     "(event_id, device_id, recorded_at, metric, value, unit) "
                     "VALUES (%s, 'role-device', CURRENT_TIMESTAMP, 'temperature', 20, 'celsius')",
                     (str(uuid.uuid4()),))
        self.conn.commit()
        self.reset_role()

        self.assume_role("cdrl_operator")
        self.assertEqual(self.execute("SELECT count(*) FROM telemetry_measurements"), [(1,)])
        self.reset_role()

    def test_reader_cannot_insert(self):
        self.assume_role("cdrl_reader")
        with self.assertRaises(errors.InsufficientPrivilege):
            self.execute("INSERT INTO devices(device_id, device_name) VALUES ('denied', 'Denied')")
        self.reset_role()

    def test_writer_cannot_read_telemetry(self):
        self.assume_role("cdrl_writer")
        with self.assertRaises(errors.InsufficientPrivilege):
            self.execute("SELECT count(*) FROM telemetry_measurements")
        self.reset_role()

    def test_operator_cannot_modify_devices(self):
        self.assume_role("cdrl_operator")
        with self.assertRaises(errors.InsufficientPrivilege):
            self.execute("UPDATE devices SET status = 'inactive' WHERE device_id = 'role-device'")
        self.reset_role()


if __name__ == "__main__":
    unittest.main()