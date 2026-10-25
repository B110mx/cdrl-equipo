import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[1]


class TestDocumentVersionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validators = {}
        for version, filename in (
            (1, "M05-event-document-schema.json"),
            (2, "M06-event-document-schema-v2.json"),
            (3, "M07-event-document-schema-v3.json"),
        ):
            schema = json.loads(
                (ROOT / "docs" / filename).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            cls.validators[version] = Draft202012Validator(
                schema, format_checker=FormatChecker())

        cls.fixtures = {
            "legacy": json.loads(
                (ROOT / "fixtures" / "document_data.json").read_text(
                    encoding="utf-8")),
            "transition": json.loads(
                (ROOT / "fixtures" /
                 "m07-document-data-transition-v2.json").read_text(
                    encoding="utf-8")),
            "v2": json.loads(
                (ROOT / "fixtures" / "m06-document-data-v2.json").read_text(
                    encoding="utf-8")),
            "v3": json.loads(
                (ROOT / "fixtures" / "m07-document-data-v3.json").read_text(
                    encoding="utf-8")),
        }

    def test_fixtures_validan_con_su_esquema_y_marcador_esperado(self):
        for event in self.fixtures["legacy"]:
            self.assertNotIn("schema_version", event)
            self.validators[1].validate(event)
        for event in self.fixtures["transition"]:
            self.assertEqual(event["schema_version"], 2)
            self.validators[2].validate(event)
        for event in self.fixtures["v2"]:
            self.assertEqual(event["schema_version"], 2)
            self.validators[2].validate(event)
        for event in self.fixtures["v3"]:
            self.assertEqual(event["schema_version"], 3)
            self.validators[3].validate(event)

    def test_limite_v1_v2_y_v3_requieren_su_version(self):
        legacy = deepcopy(self.fixtures["legacy"][0])
        current_v2 = deepcopy(self.fixtures["v2"][0])
        current_v3 = deepcopy(self.fixtures["v3"][0])

        with self.assertRaises(ValidationError):
            self.validators[3].validate(legacy)
        with self.assertRaises(ValidationError):
            self.validators[1].validate(current_v2)
        with self.assertRaises(ValidationError):
            self.validators[2].validate(current_v3)

    def test_fallo_declarado_version_v3_no_acepta_marcador_v2(self):
        invalid = deepcopy(self.fixtures["v3"][0])
        invalid["schema_version"] = 2

        with self.assertRaises(ValidationError):
            self.validators[3].validate(invalid)

    def test_v3_agrega_quality_y_conserva_reglas_de_v2(self):
        v2 = deepcopy(self.validators[2].schema)
        v3 = deepcopy(self.validators[3].schema)

        self.assertIn("quality", v3["required"])
        self.assertEqual(
            v3["properties"]["quality"]["enum"],
            ["good", "uncertain", "unknown"],
        )
        v3["required"].remove("quality")
        v3["properties"].pop("quality")
        for schema in (v2, v3):
            schema.pop("title")
            schema.pop("description")
            schema["properties"]["schema_version"]["const"] = "VERSION"

        self.assertEqual(v2, v3)


if __name__ == "__main__":
    unittest.main()
