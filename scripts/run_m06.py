"""Demuestra evolución, auditoría y recuperación controlada de M06."""

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision
from src.document_store import DocumentEventStore, DuplicateEventError


AUDIT_ID = "m06-update-018f47a0-79f2-7c19-bc7f-1a26d47e9502"
FORBIDDEN_AUDIT_TERMS = ("secret", "password", "token", "connection")


def canonical_document(document):
    if document is None:
        return None
    clean = deepcopy(document)
    clean.pop("ingested_at", None)
    return clean


def checksum(document):
    if document is None:
        return None
    payload = json.dumps(
        canonical_document(document), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def contains_forbidden_audit_data(record):
    serialized = json.dumps(record, ensure_ascii=False).lower()
    return any(term in serialized for term in FORBIDDEN_AUDIT_TERMS)


def ensure_fixture(store, fixture):
    existing = store.get_event(fixture["event_id"])
    if existing is not None and canonical_document(existing) != fixture:
        store.delete_event(fixture["event_id"])
    try:
        store.put_event_idempotent(fixture)
    except DuplicateEventError:
        store.delete_event(fixture["event_id"])
        store.put_event_idempotent(fixture)


def main():
    store = DocumentEventStore()
    legacy_fixture = json.loads(
        (ROOT / "fixtures/document_data.json").read_text(encoding="utf-8"))[0]
    v2_fixture = json.loads(
        (ROOT / "fixtures/m06-document-data-v2.json").read_text(
            encoding="utf-8"))[0]

    ensure_fixture(store, v2_fixture)
    legacy = store.get_event(legacy_fixture["event_id"])
    version_two = store.get_event(v2_fixture["event_id"])

    audited = store.update_event_audited(
        v2_fixture["event_id"],
        {"metadata": {"source": "synthetic-m06", "audited": True}},
        audit_id=AUDIT_ID,
    )
    stored_audit = store.get_audit(AUDIT_ID)

    failure_declared = store.delete_event(v2_fixture["event_id"])
    absent_during_failure = store.get_event(v2_fixture["event_id"]) is None
    started = perf_counter_ns()
    recovery = store.put_event_idempotent(v2_fixture)
    duration_ms = round((perf_counter_ns() - started) / 1_000_000, 3)
    recovered = store.get_event(v2_fixture["event_id"])
    recovered_matches = canonical_document(recovered) == v2_fixture

    cases = {
        "normal_versions_coexist": (
            legacy is not None
            and legacy.get("schema_version", 1) == 1
            and version_two is not None
            and version_two.get("schema_version") == 2
        ),
        "boundary_legacy_without_explicit_version": (
            legacy is not None and "schema_version" not in legacy
        ),
        "boundary_audit_contains_no_secrets": (
            stored_audit is not None
            and stored_audit["operation"] == "update_event"
            and stored_audit["changed_fields"] == ["metadata"]
            and not contains_forbidden_audit_data(stored_audit)
        ),
        "declared_failure_removed_fixture": (
            failure_declared is True and absent_during_failure
        ),
        "recovery_restored_fixture": (
            recovery["created"] is True and recovered_matches
        ),
    }
    report = {
        "module": "m06-evolution-audit-recovery",
        "status": "passed" if all(cases.values()) else "failed",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "versioned-coexistence",
        "schema_versions_observed": [1, 2],
        "audit": {
            "audit_id": audited["audit"]["audit_id"],
            "operation": audited["audit"]["operation"],
            "outcome": audited["audit"]["outcome"],
            "changed_fields": audited["audit"]["changed_fields"],
            "contains_forbidden_terms": contains_forbidden_audit_data(
                audited["audit"]),
        },
        "recovery": {
            "fixture": "fixtures/m06-document-data-v2.json",
            "duration_ms": duration_ms,
            "records_recovered": 1 if recovered_matches else 0,
            "expected_checksum_sha256": checksum(v2_fixture),
            "recovered_checksum_sha256": checksum(recovered),
        },
        "cases": {
            name: {"status": "passed" if passed else "failed"}
            for name, passed in cases.items()
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/m06-run.json").write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
