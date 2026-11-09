"""Pruebas M09 de mínimo privilegio, auditoría y remediación."""

import json
import unittest

from botocore.exceptions import ClientError

from src.access_control import (
    AccessDeniedError,
    AuthorizedDocumentStore,
    make_audit_event,
)
from src.document_store import DocumentEventStore


class FakeDocumentStore:
    def __init__(self):
        self.calls = []
        self.events = {
            "evt-m09-synthetic": {"event_id": "evt-m09-synthetic"},
        }

    def get_event(self, event_id):
        self.calls.append(("get_event", event_id))
        return self.events.get(event_id)

    def put_event_idempotent(self, event):
        self.calls.append(("put_event_idempotent", event["event_id"]))
        created = event["event_id"] not in self.events
        self.events.setdefault(event["event_id"], event)
        return {"created": created, "event": self.events[event["event_id"]]}

    def delete_event(self, event_id):
        self.calls.append(("delete_event", event_id))
        return self.events.pop(event_id, None) is not None

    def get_audit(self, audit_id):
        self.calls.append(("get_audit", audit_id))
        return {"audit_id": audit_id}


class InMemoryAuditClient:
    def __init__(self):
        self.items = {}

    def put_item(self, **request):
        audit_id = request["Item"]["audit_id"]["S"]
        if audit_id in self.items:
            raise ClientError({
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "synthetic duplicate",
                },
            }, "PutItem")
        self.items[audit_id] = request["Item"]

    def get_item(self, **request):
        audit_id = request["Key"]["audit_id"]["S"]
        item = self.items.get(audit_id)
        return {"Item": item} if item else {}


class TestM09Seguridad(unittest.TestCase):
    def setUp(self):
        self.backend = FakeDocumentStore()
        self.audit = []

    def facade(self, role):
        return AuthorizedDocumentStore(
            self.backend, role, f"role:{role}", self.audit.append)

    def test_normal_writer_escribe_y_audita_resultado(self):
        event = {"event_id": "evt-m09-new"}
        result = self.facade("writer").put_event_idempotent(event)

        self.assertTrue(result["created"])
        self.assertEqual(
            self.backend.calls, [("put_event_idempotent", "evt-m09-new")])
        self.assertEqual(self.audit[0]["actor"], "role:writer")
        self.assertEqual(self.audit[0]["action"], "write")
        self.assertEqual(self.audit[0]["resource"], "events:evt-m09-new")
        self.assertEqual(self.audit[0]["result"], "succeeded")

    def test_limit_reader_no_escribe_y_reporta_codigo(self):
        attempted = {
            "event_id": "evt-m09-denied",
            "metadata": {"opaque": "value-that-must-not-be-audited"},
        }

        with self.assertRaises(AccessDeniedError) as denied:
            self.facade("reader").put_event_idempotent(attempted)

        self.assertEqual(denied.exception.code, "ACCESS_DENIED")
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.audit[0]["result"], "denied")
        self.assertNotIn(
            "value-that-must-not-be-audited",
            json.dumps(self.audit, ensure_ascii=False),
        )

    def test_limit_auditor_no_lee_eventos_y_si_consulta_auditoria(self):
        auditor = self.facade("auditor")

        with self.assertRaises(AccessDeniedError) as denied:
            auditor.get_event("evt-m09-synthetic")
        audit = auditor.get_audit("audit-m09-synthetic")

        self.assertEqual(denied.exception.code, "ACCESS_DENIED")
        self.assertEqual(audit["audit_id"], "audit-m09-synthetic")
        self.assertEqual(
            self.backend.calls, [("get_audit", "audit-m09-synthetic")])
        self.assertEqual(
            [event["result"] for event in self.audit],
            ["denied", "succeeded"],
        )

    def test_declared_failure_writer_no_administra_eventos(self):
        with self.assertRaises(AccessDeniedError) as denied:
            self.facade("writer").delete_event("evt-m09-synthetic")

        self.assertEqual(denied.exception.code, "ACCESS_DENIED")
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(denied.exception.audit_event["action"], "administer")
        self.assertEqual(denied.exception.audit_event["result"], "denied")

    def test_remediation_impide_que_el_abuso_llegue_al_backend(self):
        direct = self.backend.get_event("evt-m09-synthetic")
        calls_before_guard = list(self.backend.calls)

        with self.assertRaises(AccessDeniedError) as denied:
            self.facade("auditor").get_event("evt-m09-synthetic")

        self.assertIsNotNone(direct)
        self.assertEqual(denied.exception.code, "ACCESS_DENIED")
        self.assertEqual(self.backend.calls, calls_before_guard)
        self.assertEqual(self.audit[-1]["result"], "denied")

    def test_auditoria_reproducible_no_sobrescribe_registros(self):
        client = InMemoryAuditClient()
        store = DocumentEventStore(client=client, audit_table_name="audit")
        event = make_audit_event(
            "role:reader",
            "read",
            "events:evt-m09-synthetic",
            "denied",
            occurred_at="2026-11-08T00:00:00Z",
        )

        first = store.record_audit_event(event, audit_id="audit-m09-stable")
        repeated = store.record_audit_event(event, audit_id="audit-m09-stable")

        self.assertEqual(first, repeated)
        self.assertEqual(len(client.items), 1)


if __name__ == "__main__":
    unittest.main()
