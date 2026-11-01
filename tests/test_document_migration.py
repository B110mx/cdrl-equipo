"""Pruebas reales de compatibilidad, migración repetible y rollback M07."""

import json
import unittest
import uuid
from copy import deepcopy
from pathlib import Path

from src.document_migration import DocumentMigrator
from src.document_store import DocumentEventStore, InvalidEventError


ROOT = Path(__file__).resolve().parents[1]


def comparable(document):
    value = deepcopy(document)
    value.pop("ingested_at", None)
    return value


class TestDocumentMigration(unittest.TestCase):
    """Ejecuta M07 contra DynamoDB Local, sin mocks ni datos personales."""

    @classmethod
    def setUpClass(cls):
        cls.store = DocumentEventStore()
        cls.migrator = DocumentMigrator(cls.store)
        cls.legacy = json.loads(
            (ROOT / "fixtures/document_data.json").read_text(encoding="utf-8")
        )[0]
        cls.transition = json.loads(
            (ROOT / "fixtures/m07-document-data-transition-v2.json").read_text(
                encoding="utf-8"
            )
        )[0]

    def setUp(self):
        self.created_ids = []

    def tearDown(self):
        for event_id in self.created_ids:
            self.store.delete_event(event_id)

    def synthetic_copy(self, fixture, label):
        document = deepcopy(fixture)
        document["event_id"] = str(uuid.uuid4())
        document["device_id"] = f"sensor-m07-{label}"
        document.pop("ingested_at", None)
        self.created_ids.append(document["event_id"])
        return document

    def test_normal_v2_migrates_to_v3_without_losing_business_data(self):
        original = self.synthetic_copy(self.transition, "normal")
        stored = self.store.create_event(original)

        result = self.migrator.migrate_event(original["event_id"])
        migrated = self.store.get_event(original["event_id"])

        self.assertTrue(result["changed"])
        self.assertEqual((result["from_version"], result["to_version"]), (2, 3))
        self.assertEqual(migrated["schema_version"], 3)
        self.assertEqual(migrated["quality"], "unknown")
        for field in ("event_id", "device_id", "recorded_at", "metric", "value", "unit"):
            self.assertEqual(migrated[field], stored[field])

    def test_limit_legacy_v1_remains_readable_during_transition(self):
        legacy = self.synthetic_copy(self.legacy, "legacy")
        original = self.store.create_event(legacy)

        current = self.store.get_event(legacy["event_id"])

        self.assertNotIn("schema_version", current)
        self.assertEqual(comparable(current), comparable(original))
        self.assertEqual(self.store.validate(current)["event_id"], legacy["event_id"])

    def test_limit_repeated_migration_is_idempotent(self):
        document = self.synthetic_copy(self.transition, "repeat-migration")
        self.store.create_event(document)

        first = self.migrator.migrate_event(document["event_id"])
        second = self.migrator.migrate_event(document["event_id"])

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["event"], second["event"])

    def test_rollback_restores_v2_and_is_repeatable(self):
        original = self.synthetic_copy(self.transition, "rollback")
        self.store.create_event(original)
        self.migrator.migrate_event(original["event_id"])

        first = self.migrator.rollback_event(original["event_id"], target_version=2)
        second = self.migrator.rollback_event(original["event_id"], target_version=2)

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(comparable(first["event"]), original)
        self.assertEqual(first["event"], second["event"])

    def test_declared_failure_invalid_quality_is_rejected_without_mutation(self):
        original = self.synthetic_copy(self.transition, "invalid-quality")
        self.store.create_event(original)

        with self.assertRaises(InvalidEventError):
            self.migrator.migrate_event(
                original["event_id"], default_quality="not-declared"
            )

        current = self.store.get_event(original["event_id"])
        self.assertEqual(comparable(current), original)


if __name__ == "__main__":
    unittest.main()
