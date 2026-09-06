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
    VALID_METRICS = {
        "temperature": {"min": -80.0, "max": 200.0},
        "humidity": {"min": 0.0, "max": 100.0},
        "battery_voltage": {"min": 0.0, "max": 100.0}  # Rango supuesto, verificar contrato
    }
    VALID_UNITS = {
        "temperature": {"celsius"},
        "humidity": {"percent"},
        "battery_voltage": {"volt"}
    }
    MAX_FUTURE_MINUTES = 5
    MAX_DEVICE_ID_LENGTH = 64
    ALLOWED_DEVICE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:@")
    MAX_METADATA_BYTES = 2048
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
    def _is_valid_device_id(device_id: str) -> bool:
        """Valida device_id: no vacío, longitud ≤64 y caracteres permitidos."""
        if not isinstance(device_id, str) or not device_id.strip():
            return False
        device_id = device_id.strip()
        if len(device_id) > TelemetryManager.MAX_DEVICE_ID_LENGTH:
            return False
        # Comprobar que todos los caracteres están en el conjunto permitido
        return all(ch in TelemetryManager.ALLOWED_DEVICE_ID_CHARS for ch in device_id)

    @staticmethod
    def _is_valid_metadata(metadata: Any) -> bool:
        """La metadata debe ser un dict, serializable a JSON y ≤2048 bytes."""
        if not isinstance(metadata, dict):
            return False
        try:
            json_str = json.dumps(metadata)
            return len(json_str.encode('utf-8')) <= TelemetryManager.MAX_METADATA_BYTES
        except TypeError:
            return False

    def validate_telemetry_data(
        self,
        event_id: str,
        device_id: str,
        recorded_at: datetime,
        metric: str,
        value: float,
        unit: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Valida todos los campos según el contrato.
        Lanza TelemetryValidationError si algún campo no cumple.
        """
        # event_id: UUID no vacío
        if not event_id or not self._is_valid_uuid(event_id):
            raise TelemetryValidationError("event_id debe ser un UUID válido y no vacío.")

        # device_id: no vacío, longitud ≤64, caracteres permitidos
        if not self._is_valid_device_id(device_id):
            raise TelemetryValidationError(
                f"device_id debe tener entre 1 y {self.MAX_DEVICE_ID_LENGTH} caracteres, "
                f"y solo incluir letras, números, '-', '_', '.', ':', '@'."
            )

        # recorded_at: datetime con zona horaria
        if not isinstance(recorded_at, datetime):
            raise TelemetryValidationError("recorded_at debe ser un objeto datetime.")
        if recorded_at.tzinfo is None or recorded_at.tzinfo.utcoffset(recorded_at) is None:
            raise TelemetryValidationError("recorded_at debe incluir zona horaria.")
        now = datetime.now(timezone.utc)
        recorded_utc = recorded_at.astimezone(timezone.utc)
        if recorded_utc - now > timedelta(minutes=self.MAX_FUTURE_MINUTES):
            raise TelemetryValidationError(
                f"recorded_at no puede estar más de {self.MAX_FUTURE_MINUTES} minutos en el futuro."
            )

        # metric: debe ser una de las métricas válidas
        if metric not in self.VALID_METRICS:
            raise TelemetryValidationError(f"Métrica '{metric}' no soportada.")

        # value: numérico y dentro del rango de la métrica
        if not isinstance(value, (int, float)):
            raise TelemetryValidationError("value debe ser un número.")
        value_float = float(value)
        range_min = self.VALID_METRICS[metric]["min"]
        range_max = self.VALID_METRICS[metric]["max"]
        if value_float < range_min or value_float > range_max:
            raise TelemetryValidationError(
                f"value para {metric} debe estar entre {range_min} y {range_max}."
            )

        # unit: debe ser válido para la métrica
        if unit not in self.VALID_UNITS.get(metric, set()):
            raise TelemetryValidationError(f"Unit '{unit}' no válida para métrica '{metric}'.")

        # metadata: dict, serializable y ≤2048 bytes
        if metadata is not None and not self._is_valid_metadata(metadata):
            raise TelemetryValidationError(
                "metadata debe ser un diccionario JSON serializable de máximo 2048 bytes."
            )

    def insert_measurement(
        self,
        event_id: str,
        device_id: str,
        recorded_at: datetime,
        metric: str,
        value: float,
        unit: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Inserta una medición en la tabla telemetry_measurements.
        Realiza la validación antes de insertar.
        """
        self.validate_telemetry_data(event_id, device_id, recorded_at, metric, value, unit, metadata)

        # Normalizar
        device_id = device_id.strip()
        if metadata is None:
            metadata_json = json.dumps({})
        else:
            metadata_json = json.dumps(metadata)

        cursor = self.db.get_cursor()
        try:
            cursor.execute(
                f"""
                INSERT INTO {self.TABLE_NAME} 
                (event_id, device_id, recorded_at, metric, value, unit, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (event_id, device_id, recorded_at, metric, float(value), unit, metadata_json)
            )
            self.db.connection.commit()
        except Exception as e:
            self.db.connection.rollback()
            raise RuntimeError(f"Error al insertar la medición: {e}")