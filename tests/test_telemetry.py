"""Pruebas unitarias para TelemetryManager usando unittest."""
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import json

from freezegun import freeze_time

from src.db import DatabaseConnection
from src.telemetry import TelemetryManager, TelemetryValidationError


class TestTelemetryValidation(unittest.TestCase):
    """Pruebas de validación de datos de telemetría."""

    def setUp(self):
        self.mock_db = MagicMock(spec=DatabaseConnection)
        self.manager = TelemetryManager(self.mock_db)

    def _valid_data(self):
        return {
            "event_id": str(uuid.uuid4()),
            "device_id": "sensor-001",
            "recorded_at": datetime.now(timezone.utc),
            "metric": "temperature",
            "value": 23.75,
            "unit": "celsius",
            "metadata": {"location": "lab", "accuracy": 0.1}
        }

    # ---------- Caso normal ----------
    def test_validate_normal_temperature(self):
        data = self._valid_data()
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para datos normales")

    # ---------- Casos límite: temperaturas -80 y 200 ----------
    def test_validate_boundary_temperature_min(self):
        data = self._valid_data()
        data["value"] = -80.0
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para -80")

    def test_validate_boundary_temperature_max(self):
        data = self._valid_data()
        data["value"] = 200.0
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para 200")

    def test_validate_temperature_below_min_fails(self):
        data = self._valid_data()
        data["value"] = -81.0
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_temperature_above_max_fails(self):
        data = self._valid_data()
        data["value"] = 201.0
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    # ---------- Caso límite: fecha exactamente 5 minutos en el futuro ----------
    @freeze_time("2025-01-01 12:00:00")
    def test_validate_future_exactly_5_minutes_accepted(self):
        data = self._valid_data()
        data["recorded_at"] = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para fecha exactamente 5 min en futuro")

    @freeze_time("2025-01-01 12:00:00")
    def test_validate_future_more_than_5_minutes_fails(self):
        data = self._valid_data()
        data["recorded_at"] = datetime.now(timezone.utc) + timedelta(minutes=6)
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    # ---------- Fallo declarado: event_id vacío ----------
    def test_validate_empty_event_id_fails(self):
        data = self._valid_data()
        data["event_id"] = ""
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    # Otras validaciones
    def test_validate_invalid_uuid_fails(self):
        data = self._valid_data()
        data["event_id"] = "not-a-uuid"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_missing_timezone_fails(self):
        data = self._valid_data()
        data["recorded_at"] = datetime.now()
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_invalid_unit_fails(self):
        data = self._valid_data()
        data["unit"] = "fahrenheit"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_invalid_metric_fails(self):
        data = self._valid_data()
        data["metric"] = "pressure"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_invalid_metadata_fails(self):
        data = self._valid_data()
        data["metadata"] = "no es dict"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_metadata_exceeds_bytes_fails(self):
        data = self._valid_data()
        data["metadata"] = {"large_field": "x" * 2049}
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_device_id_too_long_fails(self):
        data = self._valid_data()
        data["device_id"] = "a" * 65
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_device_id_invalid_chars_fails(self):
        data = self._valid_data()
        data["device_id"] = "sensor with spaces!"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_device_id_colon_rejected(self):
        data = self._valid_data()
        data["device_id"] = "sensor:001"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_device_id_at_rejected(self):
        data = self._valid_data()
        data["device_id"] = "sensor@001"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_bool_value_fails(self):
        data = self._valid_data()
        data["value"] = True
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_nan_value_fails(self):
        data = self._valid_data()
        data["value"] = float('nan')
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)


class TestTelemetryInsertion(unittest.TestCase):
    """Pruebas de inserción con mocks de base de datos y verificación de SQL."""

    def setUp(self):
        self.mock_db = MagicMock(spec=DatabaseConnection)
        self.mock_cursor = MagicMock()
        self.mock_db.get_cursor.return_value = self.mock_cursor
        self.mock_db.connection = MagicMock()
        self.mock_db.connection.closed = False
        self.manager = TelemetryManager(self.mock_db)

    def _valid_data(self):
        return {
            "event_id": str(uuid.uuid4()),
            "device_id": "sensor-001",
            "recorded_at": datetime.now(timezone.utc),
            "metric": "temperature",
            "value": 23.75,
            "unit": "celsius",
            "metadata": {"location": "lab"}
        }

    def test_insert_measurement_success(self):
        data = self._valid_data()
        self.manager.insert_measurement(**data)

        self.mock_cursor.execute.assert_called_once()
        args, kwargs = self.mock_cursor.execute.call_args
        sql = args[0]
        params = args[1]

        self.assertIn("INSERT INTO telemetry_measurements", sql)
        self.assertIn("event_id", sql)
        self.assertIn("device_id", sql)
        self.assertIn("recorded_at", sql)
        self.assertIn("metric", sql)
        self.assertIn("value", sql)
        self.assertIn("unit", sql)
        self.assertIn("metadata", sql)
        self.assertNotIn("temperature", sql)

        self.assertEqual(params[0], data["event_id"])
        self.assertEqual(params[1], data["device_id"])
        self.assertEqual(params[3], "temperature")
        self.assertEqual(params[4], 23.75)
        self.assertEqual(params[5], "celsius")
        self.assertEqual(params[6], json.dumps(data["metadata"]))

        self.mock_db.connection.commit.assert_called_once()
        self.mock_db.connection.rollback.assert_not_called()

    def test_insert_measurement_db_error_rolls_back(self):
        data = self._valid_data()
        self.mock_cursor.execute.side_effect = Exception("DB error")

        with self.assertRaises(RuntimeError):
            self.manager.insert_measurement(**data)

        self.mock_db.connection.rollback.assert_called_once()
        self.mock_db.connection.commit.assert_not_called()

    def test_insert_measurement_invalid_data_raises_validation_error(self):
        data = self._valid_data()
        data["event_id"] = ""
        with self.assertRaises(TelemetryValidationError):
            self.manager.insert_measurement(**data)
        self.mock_cursor.execute.assert_not_called()


class TestDatabaseConnectionConfig(unittest.TestCase):
    """Pruebas de configuración de conexión usando variables de entorno sintéticas."""

    def test_config_reads_env_vars(self):
        with patch.dict('os.environ', {
            'POSTGRES_HOST': 'synthetic-host',
            'POSTGRES_PORT': '5433',
            'POSTGRES_DB': 'synthetic_db',
            'POSTGRES_USER': 'synthetic_user',
            'POSTGRES_PASSWORD': 'synthetic_pass'
        }):
            db = DatabaseConnection()
            self.assertEqual(db.host, 'synthetic-host')
            self.assertEqual(db.port, 5433)
            self.assertEqual(db.dbname, 'synthetic_db')
            self.assertEqual(db.user, 'synthetic_user')
            self.assertEqual(db.password, 'synthetic_pass')

    @patch('src.db.psycopg2.connect')
    def test_connect_success(self, mock_connect):
        mock_connect.return_value = MagicMock()
        db = DatabaseConnection()
        conn = db.connect()
        self.assertIsNotNone(conn)
        mock_connect.assert_called_once()

    @patch('src.db.psycopg2.connect')
    def test_connect_failure_raises_connection_error(self, mock_connect):
        from psycopg2 import OperationalError
        mock_connect.side_effect = OperationalError("connection refused")
        db = DatabaseConnection()
        with self.assertRaises(ConnectionError):
            db.connect()


if __name__ == '__main__':
    unittest.main()
