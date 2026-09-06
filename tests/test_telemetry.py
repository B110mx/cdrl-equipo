"""Pruebas unitarias para TelemetryManager usando unittest."""
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import uuid

from src.db import DatabaseConnection
from src.telemetry import TelemetryManager, TelemetryValidationError


class TestTelemetryValidation(unittest.TestCase):
    """Pruebas de validación de datos de telemetría."""

    def setUp(self):
        # Conexión mock para el manager (no se usa en validación directa)
        self.mock_db = MagicMock(spec=DatabaseConnection)
        self.manager = TelemetryManager(self.mock_db)

    def _valid_data(self):
        """Devuelve un conjunto de datos válidos base."""
        return {
            "event_id": str(uuid.uuid4()),
            "device_id": "sensor-001",
            "recorded_at": datetime.now(timezone.utc),
            "temperature": 23.75,
            "unit": "celsius",
            "metadata": {"location": "lab", "accuracy": 0.1}
        }

    # ---------- Caso normal ----------
    def test_validate_normal_temperature(self):
        """Temperatura 23.75 celsius es aceptada."""
        data = self._valid_data()
        data["temperature"] = 23.75
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para datos normales")

    # ---------- Casos límite: temperaturas -80 y 200 ----------
    def test_validate_boundary_temperature_min(self):
        """Temperatura -80 (límite inferior) es aceptada."""
        data = self._valid_data()
        data["temperature"] = -80.0
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para -80")

    def test_validate_boundary_temperature_max(self):
        """Temperatura 200 (límite superior) es aceptada."""
        data = self._valid_data()
        data["temperature"] = 200.0
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para 200")

    def test_validate_temperature_below_min_fails(self):
        """Temperatura -81 es rechazada."""
        data = self._valid_data()
        data["temperature"] = -81.0
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_temperature_above_max_fails(self):
        """Temperatura 201 es rechazada."""
        data = self._valid_data()
        data["temperature"] = 201.0
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    # ---------- Caso límite: fecha exactamente 5 minutos en el futuro ----------
    def test_validate_future_exactly_5_minutes_accepted(self):
        """Fecha exactamente 5 minutos en el futuro es aceptada."""
        data = self._valid_data()
        now = datetime.now(timezone.utc)
        data["recorded_at"] = now + timedelta(minutes=5)
        try:
            self.manager.validate_telemetry_data(**data)
        except TelemetryValidationError:
            self.fail("validate_telemetry_data lanzó excepción para fecha exactamente 5 min en futuro")

    def test_validate_future_more_than_5_minutes_fails(self):
        """Fecha 6 minutos en el futuro es rechazada."""
        data = self._valid_data()
        now = datetime.now(timezone.utc)
        data["recorded_at"] = now + timedelta(minutes=6)
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    # ---------- Fallo declarado: event_id vacío ----------
    def test_validate_empty_event_id_fails(self):
        """event_id vacío lanza TelemetryValidationError."""
        data = self._valid_data()
        data["event_id"] = ""
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    # Otras validaciones importantes
    def test_validate_invalid_uuid_fails(self):
        data = self._valid_data()
        data["event_id"] = "not-a-uuid"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_missing_timezone_fails(self):
        data = self._valid_data()
        data["recorded_at"] = datetime.now()  # sin tzinfo
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_invalid_unit_fails(self):
        data = self._valid_data()
        data["unit"] = "fahrenheit"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)

    def test_validate_invalid_metadata_fails(self):
        data = self._valid_data()
        data["metadata"] = "no es dict"
        with self.assertRaises(TelemetryValidationError):
            self.manager.validate_telemetry_data(**data)


class TestTelemetryInsertion(unittest.TestCase):
    """Pruebas de inserción con mocks de base de datos."""

    def setUp(self):
        self.mock_db = MagicMock(spec=DatabaseConnection)
        # Simular cursor
        self.mock_cursor = MagicMock()
        self.mock_db.get_cursor.return_value = self.mock_cursor
        # Simular conexión para commit/rollback
        self.mock_db.connection = MagicMock()
        self.mock_db.connection.closed = False
        self.manager = TelemetryManager(self.mock_db)

    def _valid_data(self):
        return {
            "event_id": str(uuid.uuid4()),
            "device_id": "sensor-001",
            "recorded_at": datetime.now(timezone.utc),
            "temperature": 23.75,
            "unit": "celsius",
            "metadata": {"location": "lab"}
        }

    def test_insert_measurement_success(self):
        """Inserción exitosa ejecuta el INSERT y hace commit."""
        data = self._valid_data()
        self.mock_cursor.fetchone.return_value = None  # no importa

        self.manager.insert_measurement(**data)

        # Verificar que se llamó al cursor con la sentencia y parámetros
        self.mock_cursor.execute.assert_called_once()
        args, kwargs = self.mock_cursor.execute.call_args
        self.assertIn("INSERT INTO telemetry_measurements", args[0])
        self.assertEqual(args[1][0], data["event_id"])
        self.assertEqual(args[1][1], data["device_id"])
        # comprobar que metadata se serializa a JSON
        self.assertEqual(args[1][5], '{"location": "lab"}')
        self.mock_db.connection.commit.assert_called_once()
        self.mock_db.connection.rollback.assert_not_called()

    def test_insert_measurement_db_error_rolls_back(self):
        """Si hay error en la BD, se hace rollback y se lanza RuntimeError."""
        data = self._valid_data()
        self.mock_cursor.execute.side_effect = Exception("DB error")

        with self.assertRaises(RuntimeError):
            self.manager.insert_measurement(**data)

        self.mock_db.connection.rollback.assert_called_once()
        self.mock_db.connection.commit.assert_not_called()

    def test_insert_measurement_invalid_data_raises_validation_error(self):
        """Datos inválidos no llegan a la BD."""
        data = self._valid_data()
        data["event_id"] = ""  # inválido
        with self.assertRaises(TelemetryValidationError):
            self.manager.insert_measurement(**data)
        self.mock_cursor.execute.assert_not_called()


class TestDatabaseConnectionConfig(unittest.TestCase):
    """Pruebas de configuración de conexión usando variables de entorno sintéticas."""

    @patch.dict('os.environ', {
        'DB_HOST': 'synthetic-host',
        'DB_PORT': '5433',
        'DB_NAME': 'synthetic_db',
        'DB_USER': 'synthetic_user',
        'DB_PASSWORD': 'synthetic_pass'
    })
    def test_config_reads_env_vars(self):
        """DatabaseConnection toma los valores de las variables de entorno."""
        db = DatabaseConnection()
        self.assertEqual(db.host, 'synthetic-host')
        self.assertEqual(db.port, 5433)
        self.assertEqual(db.dbname, 'synthetic_db')
        self.assertEqual(db.user, 'synthetic_user')
        self.assertEqual(db.password, 'synthetic_pass')

    @patch('src.db.psycopg2.connect')
    def test_connect_success(self, mock_connect):
        """La conexión se establece correctamente."""
        mock_connect.return_value = MagicMock()
        db = DatabaseConnection()
        conn = db.connect()
        self.assertIsNotNone(conn)
        mock_connect.assert_called_once()

    @patch('src.db.psycopg2.connect')
    def test_connect_failure_raises_connection_error(self, mock_connect):
        """Si falla la conexión se lanza ConnectionError."""
        from psycopg2 import OperationalError
        mock_connect.side_effect = OperationalError("connection refused")
        db = DatabaseConnection()
        with self.assertRaises(ConnectionError):
            db.connect()


if __name__ == '__main__':
    unittest.main()