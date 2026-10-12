import json
import unittest
import uuid
from copy import deepcopy
from pathlib import Path

from src.document_store import DocumentEventStore


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_AUDIT_TERMS = ("secret", "password", "token", "connection")


class TestM06EvolucionAuditoria(unittest.TestCase):
    """Comprueba M06 contra las tablas reales de DynamoDB Local."""

    @classmethod
    def setUpClass(cls):
        cls.store = DocumentEventStore()
        cls.legacy = json.loads(
            (ROOT / "fixtures/document_data.json").read_text(encoding="utf-8")
        )[0]
        cls.version_two = json.loads(
            (ROOT / "fixtures/m06-document-data-v2.json").read_text(
                encoding="utf-8")
        )[0]

    def setUp(self):
        self.created_ids = []

    def tearDown(self):
        for event_id in self.created_ids:
            self.store.delete_event(event_id)

    def unique_event(self, **changes):
        event = deepcopy(self.version_two)
        event["event_id"] = str(uuid.uuid4())
        event.update(changes)
        self.created_ids.append(event["event_id"])
        return event

    def test_caso_normal_versiones_coexisten(self):
        legacy = self.store.get_event(self.legacy["event_id"])
        current = self.store.get_event(self.version_two["event_id"])
        self.assertIsNotNone(legacy)
        self.assertNotIn("schema_version", legacy)
        self.assertEqual(current["schema_version"], 2)

    def test_limite_auditoria_no_copia_secretos(self):
        event = self.unique_event()
        self.store.create_event(event)
        audit_id = f"test-audit-{event['event_id']}"
        result = self.store.update_event_audited(
            event["event_id"],
            {"metadata": {
                "source": "synthetic-test",
                "token": "value-that-must-not-be-audited",
            }},
            audit_id=audit_id,
        )
        stored = self.store.get_audit(audit_id)
        serialized = json.dumps(stored).lower()
        self.assertEqual(result["audit"]["changed_fields"], ["metadata"])
        self.assertFalse(any(term in serialized for term in FORBIDDEN_AUDIT_TERMS))
        self.assertNotIn("value-that-must-not-be-audited", serialized)

    def test_limite_zona_horaria_equivalente_consulta_utc(self):
        event = self.unique_event(
            device_id="sensor-timezone-test",
            recorded_at="2026-10-01T07:00:00-05:00",
        )
        stored = self.store.create_event(event)
        self.assertEqual(stored["recorded_at"], "2026-10-01T12:00:00Z")
        found = self.store.events_by_device(
            event["device_id"],
            "2026-10-01T11:59:59Z",
            "2026-10-01T12:00:01Z",
        )
        self.assertEqual([item["event_id"] for item in found], [event["event_id"]])

    def test_fallo_declarado_y_recuperacion_fixture(self):
        event = self.unique_event()
        self.store.create_event(event)
        self.assertTrue(self.store.delete_event(event["event_id"]))
        self.assertIsNone(self.store.get_event(event["event_id"]))
        recovered = self.store.put_event_idempotent(event)
        self.assertTrue(recovered["created"])
        self.assertEqual(
            self.store.get_event(event["event_id"])["event_id"],
            event["event_id"],
        )


if __name__ == "__main__":
    unittest.main()
