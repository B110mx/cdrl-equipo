"""Conexión a PostgreSQL usando configuración de entorno sintética."""
import os
import psycopg2
from psycopg2 import OperationalError


class DatabaseConnection:
    """Gestiona la conexión a PostgreSQL con variables de entorno."""

    def __init__(self):
        # Valores por defecto coinciden con .env.example (sintéticos)
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "5432"))
        self.dbname = os.getenv("DB_NAME", "telemetry_db")
        self.user = os.getenv("DB_USER", "telemetry_user")
        self.password = os.getenv("DB_PASSWORD", "telemetry_password")
        self.connection = None

    def connect(self):
        """Establece la conexión con PostgreSQL."""
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password
            )
            self.connection.autocommit = False
            return self.connection
        except OperationalError as e:
            raise ConnectionError(f"Error al conectar a PostgreSQL: {e}")

    def close(self):
        """Cierra la conexión si está abierta."""
        if self.connection and not self.connection.closed:
            self.connection.close()

    def get_cursor(self):
        """Devuelve un cursor a partir de la conexión activa."""
        if not self.connection or self.connection.closed:
            raise RuntimeError("No hay conexión activa. Llame a connect() primero.")
        return self.connection.cursor()