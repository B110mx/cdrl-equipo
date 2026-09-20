"""Conexión compartida para scripts: entorno cloud o configuración local Compose."""
import json
import os
import subprocess
from pathlib import Path

from src.db import DatabaseConnection

ROOT = Path(__file__).resolve().parents[1]

ROLE_ENV = {
    "migrator": ("POSTGRES_MIGRATOR_USER", "POSTGRES_MIGRATOR_PASSWORD"),
    "writer": ("POSTGRES_WRITER_USER", "POSTGRES_WRITER_PASSWORD"),
    "reader": ("POSTGRES_READER_USER", "POSTGRES_READER_PASSWORD"),
    "operator": ("POSTGRES_OPERATOR_USER", "POSTGRES_OPERATOR_PASSWORD"),
}


def compose_database_config():
    """Devuelve el servicio PostgreSQL ya resuelto por Docker Compose."""
    config = json.loads(subprocess.check_output(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT, text=True, timeout=30, stderr=subprocess.PIPE,
    ))
    return config["services"]["postgres"]


def connect_database(*, compose=False, role=None):
    """Conecta como administrador o como uno de los cuatro usuarios separados."""
    if role is not None and role not in ROLE_ENV:
        raise ValueError("Rol de conexión desconocido")
    db = DatabaseConnection()
    environment = None
    if compose:
        postgres = compose_database_config()
        environment = postgres["environment"]
        db.host = "127.0.0.1"
        db.port = int(next(
            port["published"] for port in postgres["ports"]
            if int(port["target"]) == 5432
        ))
        db.dbname = environment["POSTGRES_DB"]
        db.user = environment["POSTGRES_USER"]
        db.password = environment["POSTGRES_PASSWORD"]
    if role is not None:
        user_key, password_key = ROLE_ENV[role]
        values = environment or os.environ
        try:
            db.user = values[user_key]
            db.password = values[password_key]
        except KeyError as exc:
            raise RuntimeError("Falta configuración para el rol " + role) from exc
    db.connect()
    return db
