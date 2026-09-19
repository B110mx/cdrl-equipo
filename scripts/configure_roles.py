"""Crea usuarios de conexión y los vincula a un único rol de permisos."""
import json
import os
import subprocess
import sys
from pathlib import Path

from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime import connect_database

ROLE_USERS = (
    ("cdrl_migrator", "POSTGRES_MIGRATOR_USER", "POSTGRES_MIGRATOR_PASSWORD"),
    ("cdrl_writer", "POSTGRES_WRITER_USER", "POSTGRES_WRITER_PASSWORD"),
    ("cdrl_reader", "POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD"),
    ("cdrl_operator", "POSTGRES_OPERATOR_USER", "POSTGRES_OPERATOR_PASSWORD"),
)


def compose_environment():
    return json.loads(subprocess.check_output(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT, text=True, timeout=30, stderr=subprocess.PIPE,
    ))["services"]["postgres"]["environment"]


def configure_roles(connection, environment=None):
    environment = environment or os.environ
    with connection.cursor() as cursor:
        for role, user_key, password_key in ROLE_USERS:
            user = environment.get(user_key, role + "_user")
            password = environment.get(password_key, role + "_local_only")
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(user)))
            cursor.execute(sql.SQL("ALTER ROLE {} PASSWORD %s").format(
                sql.Identifier(user)), (password,))
            cursor.execute(sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(role), sql.Identifier(user)))
            if role == "cdrl_migrator":
                cursor.execute(sql.SQL("ALTER TABLE IF EXISTS devices OWNER TO {}").format(
                    sql.Identifier(role)))
                cursor.execute(sql.SQL(
                    "ALTER TABLE IF EXISTS telemetry_measurements OWNER TO {}"
                ).format(sql.Identifier(role)))
    connection.commit()


def main():
    db = None
    try:
        compose = "--compose" in sys.argv
        db = connect_database(compose=compose)
        configure_roles(db.connection, compose_environment() if compose else os.environ)
        print("Roles configurados")
        return 0
    except Exception as exc:
        print("No se pudieron configurar los roles: " + type(exc).__name__, file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    sys.exit(main())