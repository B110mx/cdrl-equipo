"""Pruebas unitarias de autorización por colección y auditoría saneada."""

import json
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from src.access_control import (
    AccessDeniedError,
    AuthorizedDocumentStore,
    CollectionAccessController,
    make_audit_event,
)
from src.document_store import DocumentEventStore
from scripts.render_dynamodb_iam_policy import render_policy


ROOT = Path(__file__).resolve().parents[1]


class FakeDocumentStore:
    def __init__(self):
        self.calls = []

    def get_event(self, event_id):
        self.calls.append(("get_event", event_id))
        return {"event_id": event_id}

    def create_event(self, event):
        self.calls.append(("create_event", event["event_id"]))
        return event

    def delete_event(self, event_id):
        self.calls.append(("delete_event", event_id))
        return True

    def get_audit(self, audit_id):
        self.calls.append(("get_audit", audit_id))
        return {"audit_id": audit_id}


class FakeAuditClient:
    def __init__(self):
        self.request = None

    def put_item(self, **request):
        self.request = request


class TestSecurityAccess(unittest.TestCase):
    def setUp(self):
        self.store = FakeDocumentStore()
        self.audit = []

    def authorized_store(self, role):
        return AuthorizedDocumentStore(
            self.store, role, f"role:{role}", self.audit.append)

    def test_normal_lector_lee_y_genera_auditoria_util(self):
        store = self.authorized_store("reader")
        event = store.get_event("evt-synthetic-001")

        self.assertEqual(event["event_id"], "evt-synthetic-001")
        self.assertEqual(self.store.calls, [("get_event", "evt-synthetic-001")])
        self.assertEqual(self.audit[0]["actor"], "role:reader")
        self.assertEqual(self.audit[0]["action"], "read")
        self.assertEqual(self.audit[0]["resource"], "events:evt-synthetic-001")
        self.assertEqual(self.audit[0]["result"], "succeeded")
        self.assertIn("occurred_at", self.audit[0])

    def test_limite_lector_no_escribe_y_no_invoca_el_almacen(self):
        store = self.authorized_store("reader")
        event = {"event_id": "evt-synthetic-002", "token": "synthetic-secret"}

        with self.assertRaises(AccessDeniedError) as denied:
            store.create_event(event)

        self.assertEqual(self.store.calls, [])
        self.assertEqual(denied.exception.audit_event["result"], "denied")
        self.assertEqual(self.audit, [denied.exception.audit_event])
        self.assertNotIn("token", json.dumps(self.audit).lower())
        self.assertNotIn("synthetic-secret", json.dumps(self.audit))

    def test_limite_auditor_no_lee_eventos_pero_consulta_auditoria(self):
        store = self.authorized_store("auditor")

        with self.assertRaises(AccessDeniedError):
            store.get_event("evt-synthetic-003")
        self.assertEqual(store.get_audit("audit-synthetic-001")["audit_id"],
                         "audit-synthetic-001")

        self.assertEqual(
            [entry["result"] for entry in self.audit], ["denied", "succeeded"])
        self.assertEqual(len(self.store.calls), 1)
        self.assertEqual(self.store.calls[0][0], "get_audit")

    def test_fallo_declarado_escribe_denegacion_de_administracion(self):
        store = self.authorized_store("writer")

        with self.assertRaises(AccessDeniedError):
            store.delete_event("evt-synthetic-004")

        self.assertEqual(self.store.calls, [])
        self.assertEqual(self.audit[0]["action"], "administer")
        self.assertEqual(self.audit[0]["result"], "denied")

    def test_writer_escribe_y_auditor_no_puede_escribir_evento(self):
        writer = self.authorized_store("writer")
        created = writer.create_event({"event_id": "evt-synthetic-005"})

        self.assertEqual(created["event_id"], "evt-synthetic-005")
        self.assertEqual(self.audit[0]["result"], "succeeded")
        with self.assertRaises(AccessDeniedError):
            self.authorized_store("auditor").create_event(
                {"event_id": "evt-synthetic-006"})
        self.assertEqual(self.audit[-1]["result"], "denied")
        self.assertEqual(len(self.store.calls), 1)

    def test_fixture_sintetico_de_permisos(self):
        fixture = json.loads(
            (ROOT / "fixtures/security-access-cases.json").read_text(
                encoding="utf-8"))
        controller = CollectionAccessController()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                try:
                    event = controller.authorize(
                        case["actor"], case["role"], case["collection"],
                        case["operation"], case["resource_id"])
                    actual = event["result"]
                except AccessDeniedError as denied:
                    actual = denied.audit_event["result"]
                self.assertEqual(actual, case["expected"])

    def test_contrato_de_auditoria_rechaza_carga_y_campos_no_permitidos(self):
        schema = json.loads(
            (ROOT / "docs/audit-event-schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        event = make_audit_event(
            "role:reader", "read", "events:evt-synthetic-001", "succeeded")

        self.assertEqual(list(validator.iter_errors(event)), [])
        with self.assertRaises(ValueError):
            make_audit_event(
                "person@example.com", "read", "events:evt-synthetic-001",
                "succeeded")
        self.assertIsNotNone(datetime.fromisoformat(
            event["occurred_at"].replace("Z", "+00:00")).utcoffset())
        self.assertEqual(set(event), {
            "actor", "action", "resource", "result", "occurred_at"})

    def test_persistencia_de_auditoria_guarda_solo_el_contrato(self):
        client = FakeAuditClient()
        store = DocumentEventStore(
            client=client, table_name="events", audit_table_name="audit")
        event = make_audit_event(
            "role:writer", "write", "events:evt-synthetic-007", "succeeded")

        stored = store.record_audit_event(event)

        schema = json.loads(
            (ROOT / "docs/audit-event-schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(
            schema, format_checker=FormatChecker()).validate(stored)
        self.assertEqual(client.request["TableName"], "audit")
        self.assertEqual(
            client.request["ConditionExpression"], "attribute_not_exists(audit_id)")
        self.assertEqual(
            set(stored).difference({"audit_id", "event_id", "occurred_at_audit_id"}),
            {"actor", "action", "resource", "result", "occurred_at"})

    def test_auditoria_existente_filtra_campos_no_permitidos(self):
        client = FakeAuditClient()
        store = DocumentEventStore(client=client, audit_table_name="audit")

        stored = store.record_audit(
            event_id="00000000-0000-4000-8000-000000000008",
            operation="update_event",
            changed_fields={"metadata", "token", "password"},
            audit_id="test-audit-synthetic",
            actor="role:writer",
        )

        schema = json.loads(
            (ROOT / "docs/audit-event-schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(
            schema, format_checker=FormatChecker()).validate(stored)
        self.assertEqual(stored["changed_fields"], ["metadata"])
        self.assertNotIn("token", json.dumps(stored).lower())
        self.assertNotIn("password", json.dumps(stored).lower())

    def test_politica_iam_refleja_minimo_privilegio(self):
        environment = {
            "DYNAMODB_EVENTS_TABLE_ARN": (
                "arn:aws:dynamodb:us-east-1:123456789012:table/cdrl-events"),
            "DYNAMODB_AUDIT_TABLE_ARN": (
                "arn:aws:dynamodb:us-east-1:123456789012:table/cdrl-audit"),
        }
        reader = render_policy("reader", environment)
        writer = render_policy("writer", environment)

        reader_actions = {
            action for statement in reader["Statement"]
            for action in statement["Action"]
        }
        event_arn = environment["DYNAMODB_EVENTS_TABLE_ARN"]
        audit_arn = environment["DYNAMODB_AUDIT_TABLE_ARN"]
        writer_event_actions = set()
        writer_audit_actions = set()
        for statement in writer["Statement"]:
            if event_arn in statement["Resource"] or event_arn + "/index/*" in statement["Resource"]:
                writer_event_actions.update(statement["Action"])
            if audit_arn in statement["Resource"]:
                writer_audit_actions.update(statement["Action"])
        audit_writer = render_policy("audit_writer", environment)
        reader_without_audit_arn = render_policy(
            "reader", {
                "DYNAMODB_EVENTS_TABLE_ARN": event_arn,
            })
        audit_writer_actions = {
            action for statement in audit_writer["Statement"]
            for action in statement["Action"]
        }
        audit_writer_resources = {
            resource for statement in audit_writer["Statement"]
            for resource in statement["Resource"]
        }
        self.assertEqual(reader_actions, {"dynamodb:Query"})
        self.assertEqual(writer_event_actions, {
            "dynamodb:Query", "dynamodb:PutItem", "dynamodb:TransactWriteItems"})
        self.assertEqual(writer_audit_actions, set())
        self.assertEqual(audit_writer_actions, {"dynamodb:PutItem"})
        self.assertEqual(audit_writer_resources, {audit_arn})
        self.assertEqual(len(reader_without_audit_arn["Statement"]), 1)
        with self.assertRaises(ValueError):
            render_policy("reader", {"DYNAMODB_EVENTS_TABLE_ARN": "invalid"})


if __name__ == "__main__":
    unittest.main()
