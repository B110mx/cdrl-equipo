"""Demuestra migración compatible, repetición y rollback documental de M07."""

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision
from src.document_migration import DocumentMigrator
from src.document_store import (
    DocumentEventStore,
    DuplicateEventError,
    InvalidEventError,
)


def canonical_document(document):
    clean = deepcopy(document)
    clean.pop("ingested_at", None)
    return clean


def load_fixture(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))[0]


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
    migrator = DocumentMigrator(store)
    legacy_fixture = load_fixture("fixtures/document_data.json")
    transition_fixture = load_fixture(
        "fixtures/m07-document-data-transition-v2.json")

    ensure_fixture(store, legacy_fixture)
    ensure_fixture(store, transition_fixture)
    original = store.get_event(transition_fixture["event_id"])
    legacy_before = store.get_event(legacy_fixture["event_id"])

    first_migration = migrator.migrate_event(transition_fixture["event_id"])
    second_migration = migrator.migrate_event(transition_fixture["event_id"])
    migrated = store.get_event(transition_fixture["event_id"])

    declared_failure = False
    try:
        migrator.migrate_event(
            transition_fixture["event_id"], default_quality="invalid")
    except InvalidEventError:
        declared_failure = True

    first_rollback = migrator.rollback_event(
        transition_fixture["event_id"], target_version=2)
    second_rollback = migrator.rollback_event(
        transition_fixture["event_id"], target_version=2)
    restored = store.get_event(transition_fixture["event_id"])
    legacy_after = store.get_event(legacy_fixture["event_id"])

    cases = {
        "normal_v2_migrates_to_v3": (
            first_migration["changed"] is True
            and migrated.get("schema_version") == 3
            and migrated.get("quality") == "unknown"
        ),
        "boundary_legacy_v1_remains_readable": (
            legacy_before is not None
            and legacy_after is not None
            and "schema_version" not in legacy_after
            and canonical_document(legacy_before)
            == canonical_document(legacy_after)
        ),
        "boundary_repeated_migration_is_idempotent": (
            second_migration["changed"] is False
            and second_migration["event"] == migrated
        ),
        "declared_failure_rejects_unknown_quality": declared_failure,
        "rollback_restores_v2_fixture": (
            first_rollback["changed"] is True
            and canonical_document(restored) == transition_fixture
        ),
        "boundary_repeated_rollback_is_idempotent": (
            second_rollback["changed"] is False
            and second_rollback["event"] == restored
        ),
    }
    report = {
        "module": "m07-compatible-document-migration",
        "status": "passed" if all(cases.values()) else "failed",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "expand-migrate-rollback",
        "synthetic_fixture": (
            "fixtures/m07-document-data-transition-v2.json"),
        "migration": {
            "from_version": first_migration["from_version"],
            "to_version": first_migration["to_version"],
            "default_quality": "unknown",
            "second_run_changed": second_migration["changed"],
        },
        "rollback": {
            "target_version": first_rollback["to_version"],
            "restored_original": (
                canonical_document(restored) == transition_fixture),
            "second_run_changed": second_rollback["changed"],
        },
        "cases": {
            name: {"status": "passed" if passed else "failed"}
            for name, passed in cases.items()
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/m07-run.json").write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
