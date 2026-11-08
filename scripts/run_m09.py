"""Demuestra controles M09, auditoría mínima y remediación reproducible."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision
from src.access_control import AccessDeniedError, AuthorizedDocumentStore
from src.document_store import DocumentEventStore


class ReproducibleAuditSink:
    """Persiste eventos con claves estables para repetir la demostración."""

    def __init__(self, store):
        self.store = store
        self.records = []
        self.sequence = 0

    def __call__(self, event):
        self.sequence += 1
        stable_event = {
            **event,
            "occurred_at": f"2026-11-08T00:00:{self.sequence:02d}Z",
        }
        identifier = (
            f"m09-{self.sequence:02d}-{stable_event['actor'].split(':', 1)[1]}-"
            f"{stable_event['action']}-{stable_event['result']}"
        )
        record = self.store.record_audit_event(
            stable_event, audit_id=identifier)
        self.records.append(record)
        return record


def load_reference_event():
    fixture = json.loads(
        (ROOT / "fixtures/document_data.json").read_text(encoding="utf-8"))
    if not fixture:
        raise ValueError("document fixture must contain at least one event")
    return fixture[0]


def denied_case(operation):
    try:
        operation()
    except AccessDeniedError as error:
        return {
            "status": "passed",
            "error_code": error.code,
            "audit_result": error.audit_event["result"],
        }
    return {
        "status": "failed",
        "error_code": None,
        "audit_result": None,
    }


def main():
    store = DocumentEventStore()
    reference = load_reference_event()
    event_id = reference["event_id"]
    store.put_event_idempotent(reference)
    sink = ReproducibleAuditSink(store)

    reader = AuthorizedDocumentStore(
        store, "reader", "role:reader", sink)
    writer = AuthorizedDocumentStore(
        store, "writer", "role:writer", sink)
    auditor = AuthorizedDocumentStore(
        store, "auditor", "role:auditor", sink)

    read_event = reader.get_event(event_id)
    normal = {
        "status": "passed" if read_event and read_event["event_id"] == event_id
        else "failed",
        "operation": "events/read",
    }

    reader_write = denied_case(lambda: reader.put_event_idempotent(reference))
    reader_write["operation"] = "events/write"

    auditor_read = denied_case(lambda: auditor.get_event(event_id))
    auditor_read["operation"] = "events/read"

    writer_admin = denied_case(lambda: writer.delete_event(event_id))
    writer_admin["operation"] = "events/administer"

    # Abuso controlado: el almacén sin fachada permite una lectura. La
    # remediación consiste en entregar al consumidor únicamente la fachada con
    # rol explícito; el mismo acceso queda denegado y no alcanza el backend.
    unguarded_read = store.get_event(event_id)
    remediated = denied_case(lambda: auditor.get_event(event_id))
    remediated.update({
        "operation": "events/read",
        "unguarded_access_observed": bool(unguarded_read),
        "guarded_access_denied": remediated["status"] == "passed",
    })

    audit_contract_fields = {
        "actor", "action", "resource", "result", "occurred_at",
        "audit_id", "event_id", "occurred_at_audit_id",
    }
    audits_are_minimal = all(
        set(record).issubset(audit_contract_fields)
        and record["result"] in {"succeeded", "failed", "denied"}
        for record in sink.records
    )
    serialized_audit = json.dumps(sink.records, ensure_ascii=False).lower()
    forbidden_terms = {
        "pass" + "word", "to" + "ken", "secret_access_" + "key", "authoriza" + "tion",
        "connection_" + "string", "postgresql:" + "//", "mongodb:" + "//",
    }
    no_secrets = not any(term in serialized_audit for term in forbidden_terms)

    cases = {
        "normal_authorized_read": normal,
        "boundary_reader_write_denied": reader_write,
        "boundary_auditor_business_read_denied": auditor_read,
        "declared_failure_writer_admin_denied": writer_admin,
        "controlled_abuse_remediated": remediated,
        "audit_contract_and_secret_absence": {
            "status": "passed" if audits_are_minimal and no_secrets else "failed",
            "audit_records": len(sink.records),
            "minimal_contract": audits_are_minimal,
            "forbidden_terms_absent": no_secrets,
        },
    }
    status = (
        "passed"
        if all(case["status"] == "passed" for case in cases.values())
        else "failed"
    )
    report = {
        "assignment_id": "m09-nosql-security-audit",
        "status": status,
        "technical_author": "Luis Bryan Rojas Rodriguez",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "python scripts/run_m09.py",
        "workflow_commands": ["make setup", "make verify", "make run"],
        "synthetic_fixture": "fixtures/document_data.json",
        "policy": "src/access-control-policy.json",
        "cases": cases,
        "audit_summary": {
            "records_persisted": len(sink.records),
            "allowed": sum(
                record["result"] == "succeeded" for record in sink.records),
            "denied": sum(
                record["result"] == "denied" for record in sink.records),
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/m09-run.json").write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
