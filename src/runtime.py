"""Conexión compartida para scripts: entorno cloud o configuración local Compose."""
import json
import subprocess
from pathlib import Path

from src.db import DatabaseConnection

ROOT = Path(__file__).resolve().parents[1]


def connect_database(*, compose=False):
    """Sin --compose respeta POSTGRES_*; con Compose resuelve también .env y puerto."""
    db = DatabaseConnection()
    if compose:
        config = json.loads(subprocess.check_output(
            ["docker", "compose", "config", "--format", "json"],
            cwd=ROOT, text=True, timeout=30, stderr=subprocess.PIPE,
        ))
        postgres = config["services"]["postgres"]
        environment = postgres["environment"]
        db.host = "127.0.0.1"
        db.port = int(next(
            port["published"] for port in postgres["ports"]
            if int(port["target"]) == 5432
        ))
        db.dbname = environment["POSTGRES_DB"]
        db.user = environment["POSTGRES_USER"]
        db.password = environment["POSTGRES_PASSWORD"]
    db.connect()
    return db
