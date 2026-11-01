"""Demuestra paginación estable y cursores validados para M08."""

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision
from src.document_store import (
    DocumentEventStore,
    DuplicateEventError,
    InvalidCursorError,
)


def canonical(document):
    clean = deepcopy(document)
    clean.pop("ingested_at", None)
    return clean


def ensure_event(store, event):
    existing = store.get_event(event["event_id"])
    if existing is not None and canonical(existing) != event:
        store.delete_event(event["event_id"])
    try:
        store.put_event_idempotent(event)
    except DuplicateEventError:
        store.delete_event(event["event_id"])
        store.put_event_idempotent(event)


def traverse(store, device_id, page_size, first_cursor=None):
    items = []
    page_sizes = []
    cursor = first_cursor
    while True:
        page = store.paginate_events_by_device(
            device_id, page_size=page_size, cursor=cursor)
        items.extend(page["items"])
        page_sizes.append(len(page["items"]))
        cursor = page["next_cursor"]
        if cursor is None:
            return items, page_sizes


def main():
    fixture = json.loads(
        (ROOT / "fixtures/m08-pagination.json").read_text(encoding="utf-8"))
    store = DocumentEventStore()
    device_id = fixture["device_id"]
    page_size = fixture["page_size"]
    insertions = fixture["insertions"]

    for event in insertions.values():
        store.delete_event(event["event_id"])
    for event in fixture["events"]:
        ensure_event(store, event)

    normal_items, normal_page_sizes = traverse(store, device_id, page_size)
    normal_ids = [event["event_id"] for event in normal_items]
    normal_keys = [
        f"{event['recorded_at']}#{event['event_id']}" for event in normal_items]

    empty_page = store.paginate_events_by_device(
        "sensor-m08-empty", page_size=page_size)

    first_page = store.paginate_events_by_device(
        device_id, page_size=page_size)
    for event in insertions.values():
        ensure_event(store, event)
    remaining, insertion_page_sizes = traverse(
        store, device_id, page_size, first_page["next_cursor"])
    insertion_items = first_page["items"] + remaining
    insertion_ids = [event["event_id"] for event in insertion_items]
    insertion_keys = [
        f"{event['recorded_at']}#{event['event_id']}"
        for event in insertion_items]

    rejected_cursor = False
    try:
        store.paginate_events_by_device(
            device_id, page_size=page_size + 1,
            cursor=first_page["next_cursor"])
    except InvalidCursorError:
        rejected_cursor = True

    expected_ids = [event["event_id"] for event in fixture["events"]]
    cases = {
        "normal_complete_ordered_traversal": (
            normal_ids == expected_ids
            and len(normal_ids) == len(set(normal_ids))
            and normal_keys == sorted(normal_keys)
        ),
        "boundary_empty_device": (
            empty_page == {"items": [], "next_cursor": None}),
        "boundary_final_partial_page": (
            normal_page_sizes == [5, 5, 5, 5, 4]),
        "boundary_insertions_are_positional": (
            insertions["before_cursor"]["event_id"] not in insertion_ids
            and insertions["after_cursor"]["event_id"] in insertion_ids
            and len(insertion_ids) == len(set(insertion_ids))
            and insertion_keys == sorted(insertion_keys)
        ),
        "declared_failure_mismatched_cursor_rejected": rejected_cursor,
    }
    for event in insertions.values():
        store.delete_event(event["event_id"])

    report = {
        "module": "m08-stable-document-pagination",
        "status": "passed" if all(cases.values()) else "failed",
        "technical_author": "Luis Bryan Rojas Rodriguez",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synthetic_fixture": "fixtures/m08-pagination.json",
        "page_size": page_size,
        "normal_page_sizes": normal_page_sizes,
        "insertion_page_sizes_after_first": insertion_page_sizes,
        "cases": {
            name: {"status": "passed" if passed else "failed"}
            for name, passed in cases.items()
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/m08-run.json").write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
