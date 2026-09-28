"""Casos M04 aplicados por igual a document, graph, column y object store."""
import unittest
from pathlib import Path

from fixtures.generate_fixtures import EVENTS, generate
from src.storage_comparison import DuplicateEventError, load_models

ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = EVENTS[0]["event_id"]


class TestStorageComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generate()

    def setUp(self):
        self.models = load_models(ROOT / "fixtures")

    def test_normal_lookup_by_event_id(self):
        """Caso normal: las cuatro representaciones recuperan el mismo evento."""
        for family, model in self.models.items():
            with self.subTest(family=family):
                event = model.get_event(EVENT_ID)
                self.assertIsNotNone(event)
                self.assertEqual(event["device_id"], "sensor-lab-01")
                self.assertEqual(event["metric"], "temperature")

    def test_limit_empty_device_range(self):
        """Límite 1: una consulta sin coincidencias devuelve una colección vacía."""
        for family, model in self.models.items():
            with self.subTest(family=family):
                self.assertEqual(model.events_by_device(
                    "sensor-without-events", "2026-09-27T00:00:00Z",
                    "2026-09-27T23:59:59Z"), [])

    def test_limit_inclusive_time_boundaries(self):
        """Límite 2: los extremos temporales exactos se incluyen."""
        for family, model in self.models.items():
            with self.subTest(family=family):
                events = model.events_by_device(
                    "sensor-lab-01", "2026-09-27T10:00:00Z", "2026-09-27T10:10:00Z")
                self.assertEqual([event["value"] for event in events], [20.0, -80.0, 200.0])

    def test_declared_failure_duplicate_event_id(self):
        """Fallo declarado: event_id duplicado viola la idempotencia."""
        for family, model in self.models.items():
            with self.subTest(family=family):
                with self.assertRaises(DuplicateEventError):
                    model.insert_event(EVENTS[0])

    def test_constraints_same_fixture_population(self):
        """Todas las representaciones contienen exactamente los mismos eventos."""
        expected = {event["event_id"] for event in EVENTS}
        for family, model in self.models.items():
            with self.subTest(family=family):
                actual = {event_id for event_id in expected if model.get_event(event_id)}
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
