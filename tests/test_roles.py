"""Pruebas de permisos mínimos para los roles PostgreSQL del equipo."""
import unittest
import uuid
import os

import psycopg2
from psycopg2 import errors, sql

from scripts.configure_roles import configure_roles
from scripts.migrate import apply_migrations
from src.db import DatabaseConnection

ACCESS_DENIALS = []


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
        configure_roles(self.conn)

    def tearDown(self):
        self.conn.rollback()
        self.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.conn.commit()
        self.db.close()

    def execute(self, query, parameters=None):
        with self.conn.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchall() if cursor.description else None

    def role_connection(self, role):
        key = role.removeprefix("cdrl_").upper()
        user = os.getenv("POSTGRES_" + key + "_USER", role + "_user")
        password = os.getenv("POSTGRES_" + key + "_PASSWORD", role + "_local_only")
        connection = psycopg2.connect(host=self.db.host, port=self.db.port,
                                      dbname=self.db.dbname, user=user, password=password)
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        connection.commit()
        return connection

    def assert_access_denied(self, role, operation, statement, parameters=None):
        with self.role_connection(role) as connection:
            with self.assertRaises(errors.InsufficientPrivilege) as caught:
                with connection.cursor() as cursor:
                    cursor.execute(statement, parameters)
            sqlstate = caught.exception.pgcode
            ACCESS_DENIALS.append({
                "test": self.id(),
                "role": role,
                "operation": operation,
                "status": "passed",
                "sqlstate": sqlstate,
                "expected_sqlstate": "42501",
            })
            self.assertEqual(sqlstate, "42501")

    def test_declared_permissions_are_available(self):
        with self.role_connection("cdrl_migrator") as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE TABLE migration_probe (probe_id integer)")
                cursor.execute("ALTER TABLE devices ADD COLUMN migration_marker boolean DEFAULT false")
            connection.commit()

        with self.role_connection("cdrl_reader") as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM devices")
                self.assertEqual(cursor.fetchall(), [(1,)])
                cursor.execute("SELECT count(*) FROM telemetry_measurements")

        with self.role_connection("cdrl_writer") as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO telemetry_measurements "
                               "(event_id, device_id, recorded_at, metric, value, unit) "
                               "VALUES (%s, 'role-device', CURRENT_TIMESTAMP, 'temperature', 20, 'celsius')",
                               (str(uuid.uuid4()),))
            connection.commit()

        with self.role_connection("cdrl_operator") as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT measurement_count, earliest_recorded_at,
                           latest_recorded_at, latest_ingested_at
                    FROM cdrl_operational_summary
                """)
                row = cursor.fetchone()
                self.assertEqual(row[0], 1)
                self.assertIsNotNone(row[1])
                self.assertIsNotNone(row[2])
                self.assertIsNotNone(row[3])

    def test_reader_cannot_insert(self):
        self.assert_access_denied(
            "cdrl_reader", "insert_device",
            "INSERT INTO devices(device_id, device_name) VALUES ('denied', 'Denied')")

    def test_writer_cannot_read_telemetry(self):
        self.assert_access_denied(
            "cdrl_writer", "select_telemetry",
            "SELECT count(*) FROM telemetry_measurements")

    def test_operator_cannot_read_telemetry_directly(self):
        self.assert_access_denied(
            "cdrl_operator", "select_telemetry_directly",
            "SELECT count(*) FROM telemetry_measurements")

    def test_operator_cannot_modify_devices(self):
        self.assert_access_denied(
            "cdrl_operator", "update_device",
            "UPDATE devices SET status = 'inactive' WHERE device_id = 'role-device'")

    def test_migrator_cannot_create_roles(self):
        self.assert_access_denied(
            "cdrl_migrator", "create_role", "CREATE ROLE denied_role")

    def test_public_cannot_read_future_objects(self):
        future_table = "future_probe_" + uuid.uuid4().hex
        with self.role_connection("cdrl_migrator") as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET ROLE cdrl_migrator")
                cursor.execute(sql.SQL("CREATE TABLE {} (probe_id integer)").format(
                    sql.Identifier(future_table)))
            connection.commit()
        self.assertFalse(self.execute(
            "SELECT has_schema_privilege('public', %s, 'CREATE')", (self.schema,))[0][0])
        self.assert_access_denied(
            "cdrl_operator", "select_future_object",
            sql.SQL("SELECT * FROM {}").format(sql.Identifier(future_table)))

    def test_public_cannot_execute_future_functions(self):
        future_function = "future_function_" + uuid.uuid4().hex
        with self.conn.cursor() as cursor:
            cursor.execute(sql.SQL(
                "CREATE FUNCTION {}() RETURNS integer LANGUAGE SQL AS 'SELECT 1'"
            ).format(sql.Identifier(future_function)))
        self.conn.commit()
        signature = f"{self.schema}.{future_function}()"
        self.assertFalse(self.execute(
            "SELECT has_function_privilege('public', %s, 'EXECUTE')", (signature,))[0][0])
        self.assert_access_denied(
            "cdrl_operator", "execute_future_function",
            sql.SQL("SELECT {}()").format(sql.Identifier(future_function)))

    def test_each_login_has_exactly_one_cdrl_membership(self):
        expected = {
            os.getenv("POSTGRES_MIGRATOR_USER", "cdrl_migrator_user"): "cdrl_migrator",
            os.getenv("POSTGRES_WRITER_USER", "cdrl_writer_user"): "cdrl_writer",
            os.getenv("POSTGRES_READER_USER", "cdrl_reader_user"): "cdrl_reader",
            os.getenv("POSTGRES_OPERATOR_USER", "cdrl_operator_user"): "cdrl_operator",
        }
        for user, expected_role in expected.items():
            memberships = self.execute("""
                SELECT granted.rolname
                FROM pg_auth_members AS membership
                JOIN pg_roles AS login_role ON login_role.oid = membership.member
                JOIN pg_roles AS granted ON granted.oid = membership.roleid
                WHERE login_role.rolname = %s AND granted.rolname LIKE 'cdrl_%%'
                ORDER BY granted.rolname
            """, (user,))
            self.assertEqual(memberships, [(expected_role,)])

    def _assert_writer_accepts_temperature(self, value):
        event_id = str(uuid.uuid4())
        with self.role_connection("cdrl_writer") as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO telemetry_measurements
                    (event_id, device_id, recorded_at, metric, value, unit)
                    VALUES (%s, 'role-device', CURRENT_TIMESTAMP, 'temperature', %s, 'celsius')
                """, (event_id, value))
            connection.commit()
        stored = self.execute(
            "SELECT value FROM telemetry_measurements WHERE event_id = %s", (event_id,))
        self.assertEqual(float(stored[0][0]), float(value))

    def test_limits_writer_temperature_minimum(self):
        """Límite 1: el escritor acepta exactamente -80 grados."""
        self._assert_writer_accepts_temperature(-80)

    def test_limits_writer_temperature_maximum(self):
        """Límite 2: el escritor acepta exactamente 200 grados."""
        self._assert_writer_accepts_temperature(200)

    def test_declared_failure_writer_rejects_null_metric(self):
        """Fallo declarado: metric NULL se rechaza con SQLSTATE 23502."""
        with self.role_connection("cdrl_writer") as connection:
            with self.assertRaises(errors.NotNullViolation) as caught:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO telemetry_measurements
                        (event_id, device_id, recorded_at, metric, value, unit)
                        VALUES (%s, 'role-device', CURRENT_TIMESTAMP, NULL, 20.0, 'celsius')
                    """, (str(uuid.uuid4()),))
            self.assertEqual(caught.exception.pgcode, "23502")


if __name__ == "__main__":
    unittest.main()
