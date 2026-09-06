"""Gestión de telemetría: validación e inserción en PostgreSQL."""
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from src.db import DatabaseConnection


class TelemetryValidationError(ValueError):
    """Excepción personalizada para errores de validación de telemetría."""
    pass


class TelemetryManager:
    """Clase para validar y almacenar mediciones de telemetría."""

    # Constantes según contrato de datos
    VALID_UNITS = {"celsius"}
    MIN_TEMPERATURE = -80.0
    MAX_TEMPERATURE = 200.0
    MAX_FUTURE_MINUTES = 5
    MAX_DEVICE_ID_LENGTH = 50
    TABLE_NAME = "telemetry_measurements"

    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection

    @staticmethod
    def _is_valid_uuid(value: str) -> bool:
        """Comprueba si value es un UUID válido."""
        try:
            uuid.UUID(str(value))
            return True
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def _is_valid_metadata(metadata: Any) -> bool:
        """La metadata debe ser un dict y serializable a JSON."""
        if not isinstance(metadata, dict):
            return False
        try:
            json.dumps(metadata)
            return True
        except TypeError:
            return False

    @staticmethod
    def validate_telemetry_data(
        event_id: str,
        device_id: str,
        recorded_at: datetime,
        temperature: float,
        unit: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Valida todos los campos según el contrato.
        Lanza TelemetryValidationError si algún campo no cumple.
        """
        # event_id: UUID no vacío
        if not event_id or not TelemetryManager._is_valid_uuid(event_id):
            raise TelemetryValidationError("event_id debe ser un UUID válido y no vacío.")

        # device_id: string no vacío y longitud máxima
        if not isinstance(device_id, str) or not device_id.strip():
            raise TelemetryValidationError("device_id no puede estar vacío.")
        if len(device_id.strip()) > TelemetryManager.MAX_DEVICE_ID_LENGTH:
            raise TelemetryValidationError(
                f"device_id excede los {TelemetryManager.MAX_DEVICE_ID_LENGTH} caracteres."
            )

        # recorded_at: datetime con zona horaria (timezone-aware)
        if not isinstance(recorded_at, datetime):
            raise TelemetryValidationError("recorded_at debe ser un objeto datetime.")
        if recorded_at.tzinfo is None or recorded_at.tzinfo.utcoffset(recorded_at) is None:
            raise TelemetryValidationError("recorded_at debe incluir zona horaria.")

        # Comprobar que no sea más de MAX_FUTURE_MINUTES en el futuro
        now = datetime.now(timezone.utc)
        # Convertir a UTC para comparar
        recorded_utc = recorded_at.astimezone(timezone.utc)
        delta = recorded_utc - now
        if delta > timedelta(minutes=TelemetryManager.MAX_FUTURE_MINUTES):
            raise TelemetryValidationError(
                f"recorded_at no puede estar más de {TelemetryManager.MAX_FUTURE_MINUTES} minutos en el futuro."
            )

        # temperature: numérica y dentro de rango
        if not isinstance(temperature, (int, float)):
            raise TelemetryValidationError("temperature debe ser un número.")
        temp_float = float(temperature)
        if temp_float < TelemetryManager.MIN_TEMPERATURE or temp_float > TelemetryManager.MAX_TEMPERATURE:
            raise TelemetryValidationError(
                f"temperature debe estar entre {TelemetryManager.MIN_TEMPERATURE} y {TelemetryManager.MAX_TEMPERATURE}."
            )

        # unit: solo 'celsius'
        if unit not in TelemetryManager.VALID_UNITS:
            raise TelemetryValidationError(f"unit debe ser una de: {TelemetryManager.VALID_UNITS}")

        # metadata: debe ser dict y JSON serializable
        if metadata is not None and not TelemetryManager._is_valid_metadata(metadata):
            raise TelemetryValidationError("metadata debe ser un diccionario serializable a JSON.")

    def insert_measurement(
        self,
        event_id: str,
        device_id: str,
        recorded_at: datetime,
        temperature: float,
        unit: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Inserta una medición en la tabla telemetry_measurements.
        Realiza la validación antes de insertar.
        """
        self.validate_telemetry_data(event_id, device_id, recorded_at, temperature, unit, metadata)

        # Normalizar metadata: si es None, insertar '{}'
        if metadata is None:
            metadata_json = json.dumps({})
        else:
            metadata_json = json.dumps(metadata)

        cursor = self.db.get_cursor()
        try:
            cursor.execute(
                f"""
                INSERT INTO {self.TABLE_NAME} (event_id, device_id, recorded_at, temperature, unit, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (event_id, device_id.strip(), recorded_at, float(temperature), unit, metadata_json)
            )
            self.db.connection.commit()
        except Exception as e:
            self.db.connection.rollback()
            raise RuntimeError(f"Error al insertar la medición: {e}")
            