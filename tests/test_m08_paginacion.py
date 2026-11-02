"""Pruebas M08 contra la implementación real y DynamoDB Local."""

import json
import unittest
from copy import deepcopy
from pathlib import Path

from src.document_store import (
    DocumentEventStore,
    DuplicateEventError,
    InvalidCursorError,
)


ROOT = Path(__file__).resolve().parents[1]


def canonical(document):
    clean = deepcopy(document)
    clean.pop("ingested_at", None)
    return clean


class TestM08Paginacion(unittest.TestCase):
    """Valida recorrido, límites, inserciones y fallos del cursor real."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(
            (ROOT / "fixtures/m08-pagination.json").read_text(encoding="utf-8"))
        cls.store = DocumentEventStore()
        for event in cls.fixture["insertions"].values():
            cls.store.delete_event(event["event_id"])
        for event in cls.fixture["events"]:
            existing = cls.store.get_event(event["event_id"])
            if existing is not None and canonical(existing) != event:
                cls.store.delete_event(event["event_id"])
            try:
                cls.store.put_event_idempotent(event)
            except DuplicateEventError:
                cls.store.delete_event(event["event_id"])
                cls.store.put_event_idempotent(event)

    def tearDown(self):
        for event in self.fixture["insertions"].values():
            self.store.delete_event(event["event_id"])

    def traverse(self, cursor=None, page_size=None):
        page_size = page_size or self.fixture["page_size"]
        items = []
        sizes = []
        while True:
            page = self.store.paginate_events_by_device(
                self.fixture["device_id"], page_size=page_size, cursor=cursor)
            items.extend(page["items"])
            sizes.append(len(page["items"]))
            cursor = page["next_cursor"]
            if cursor is None:
                return items, sizes

    def test_normal_recorrido_completo_sin_omisiones(self):
        items, sizes = self.traverse()
        actual_ids = [item["event_id"] for item in items]
        expected_ids = [event["event_id"] for event in self.fixture["events"]]
        keys = [f"{item['recorded_at']}#{item['event_id']}" for item in items]

        self.assertEqual(actual_ids, expected_ids)
        self.assertEqual(len(actual_ids), len(set(actual_ids)))
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(sizes, [5, 5, 5, 5, 4])

    def test_limit_consulta_vacia_y_tamanos_inclusivos(self):
        empty = self.store.paginate_events_by_device(
            "sensor-m08-without-events", page_size=1)
        complete = self.store.paginate_events_by_device(
            self.fixture["device_id"], page_size=100)

        self.assertEqual(empty, {"items": [], "next_cursor": None})
        self.assertEqual(len(complete["items"]), 24)
        self.assertIsNone(complete["next_cursor"])

    def test_limit_inserciones_respetan_posicion_del_cursor(self):
        first = self.store.paginate_events_by_device(
            self.fixture["device_id"], page_size=self.fixture["page_size"])
        self.assertIsNotNone(first["next_cursor"])
        self.assertNotIn("=", first["next_cursor"])

        for event in self.fixture["insertions"].values():
            self.store.put_event_idempotent(event)
        remaining, sizes = self.traverse(cursor=first["next_cursor"])
        combined = first["items"] + remaining
        ids = [item["event_id"] for item in combined]
        keys = [f"{item['recorded_at']}#{item['event_id']}" for item in combined]

        self.assertNotIn(
            self.fixture["insertions"]["before_cursor"]["event_id"], ids)
        self.assertIn(
            self.fixture["insertions"]["after_cursor"]["event_id"], ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(sizes, [5, 5, 5, 5])

    def test_declared_failure_rechaza_cursor_malformado_e_incompatible(self):
        with self.assertRaises(InvalidCursorError):
            self.store.paginate_events_by_device(
                self.fixture["device_id"], page_size=5, cursor="cursor+invalido=")

        first = self.store.paginate_events_by_device(
            self.fixture["device_id"], page_size=5)
        with self.assertRaises(InvalidCursorError):
            self.store.paginate_events_by_device(
                self.fixture["device_id"], page_size=6,
                cursor=first["next_cursor"])


if __name__ == "__main__":
    unittest.main()
