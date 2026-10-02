import unittest
import uuid
from datetime import datetime, timezone
import boto3

# Importaciones precisas basadas en src/document_store.py
from src.document_store import (
    DocumentEventStore,
    DuplicateEventError,
    InvalidEventError,
    EventNotFoundError
)

class TestDocumentStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Instanciamos la clase de acceso a DynamoDB
        cls.store = DocumentEventStore()
        
    def setUp(self):
        # Documento base válido
        self.valid_event = {
            "event_id": str(uuid.uuid4()),
            "device_id": "sensor-alpha-01",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "metric": "temperature",
            "value": 25.5,
            "unit": "celsius",
            "metadata": {"location": "warehouse"}
        }

    # 1. PRUEBA DEL CASO NORMAL (CRUD)
    def test_normal_crud_operations(self):
        """Verifica que un documento válido pueda crearse, leerse, actualizarse y eliminarse."""
        # Create
        created = self.store.create_event(self.valid_event)
        self.assertEqual(created["device_id"], "sensor-alpha-01")
        
        # Read
        fetched = self.store.get_event(self.valid_event["event_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["value"], 25.5)
        
        # Update (usando update_event que permite actualizar metadatos/valores)
        updated = self.store.update_event(self.valid_event["event_id"], {"value": 26.0})
        self.assertEqual(updated["value"], 26.0)
        
        # Delete
        delete_result = self.store.delete_event(self.valid_event["event_id"])
        self.assertTrue(delete_result)
        
        # Verify Deletion
        self.assertIsNone(self.store.get_event(self.valid_event["event_id"]))

    # 2. PRUEBAS DE CASOS LÍMITE (DUPLICADO Y AUSENCIA)
    def test_limits_duplicate_insertion(self):
        """Verifica el control de inserción duplicada."""
        # Insertar primera vez
        self.store.create_event(self.valid_event)
        
        # Intentar insertar exactamente el mismo event_id usando create_event
        with self.assertRaises(DuplicateEventError):
            self.store.create_event(self.valid_event)
            
        # Limpiar
        self.store.delete_event(self.valid_event["event_id"])

    def test_limits_absence_handling(self):
        """Verifica que las operaciones manejen correctamente documentos inexistentes."""
        fake_id = str(uuid.uuid4())
        
        # Leer inexistente
        self.assertIsNone(self.store.get_event(fake_id))
        
        # Actualizar inexistente
        with self.assertRaises(EventNotFoundError):
            self.store.update_event(fake_id, {"value": 10.0})
        
        # Eliminar inexistente (debe devolver False según el código)
        delete_result = self.store.delete_event(fake_id)
        self.assertFalse(delete_result)

    # 3. PRUEBA DE FALLO DECLARADO (RECHAZO POR ESQUEMA)
    def test_declared_failure_invalid_schema_rejected(self):
        """Verifica que la validación rechace un documento que viola el esquema."""
        invalid_event = self.valid_event.copy()
        invalid_event["metric"] = "invalid_metric" 
        invalid_event["value"] = "veinticinco"     
        
        with self.assertRaises(InvalidEventError):
            self.store.create_event(invalid_event)

    # 4. COMPROBACIÓN DE USO DE ÍNDICES DECLARADOS
    def test_constraints_indexes_are_declared(self):
        """Verifica que los índices requeridos por el ADR estén creados."""
        indexes = self.store.declared_indexes()
        
        # Según el código, usa EventIdIndex y MetricUnitTimeIndex
        self.assertIn("EventIdIndex", indexes)
        self.assertIn("MetricUnitTimeIndex", indexes)

if __name__ == "__main__":
    unittest.main()