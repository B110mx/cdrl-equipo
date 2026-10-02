"""Demuestra el CRUD M05 y guarda un resultado machine-readable."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision
from src.document_store import DocumentEventStore


EVENT = {
    "event_id": "018f47a0-79f2-7c19-bc7f-1a26d47e9501",
    "device_id": "sensor-lab-05",
    "recorded_at": "2026-09-30T12:00:00Z",
    "metric": "temperature",
    "value": 24.5,
    "unit": "celsius",
    "metadata": {"source": "synthetic-m05"},
}


def main():
    store = DocumentEventStore()
    store.delete_event(EVENT["event_id"])
    created = store.create_event(EVENT)
    read = store.get_event(EVENT["event_id"])
    updated = store.update_event(EVENT["event_id"], {
        "value": 25.0,
        "metadata": {"source": "synthetic-m05", "operation": "update"},
    })
    interval = store.events_by_device(
        EVENT["device_id"], "2026-09-30T00:00:00Z", "2026-09-30T23:59:59Z")
    metric_interval = store.events_by_metric_unit(
        "temperature", "celsius", "2026-09-30T00:00:00Z", "2026-09-30T23:59:59Z")
    deleted = store.delete_event(EVENT["event_id"])
    absent = store.get_event(EVENT["event_id"])
    cases = {
        "create": created["event_id"] == EVENT["event_id"],
        "read_by_event_id_index": read is not None and read["value"] == 24.5,
        "update": updated["value"] == 25,
        "query_by_device_time_key": len(interval) == 1,
        "query_by_metric_unit_index": any(
            event["event_id"] == EVENT["event_id"] for event in metric_interval),
        "delete": deleted is True,
        "absence_after_delete": absent is None,
    }
    report = {
        "module": "m05-document-store-crud",
        "status": "passed" if all(cases.values()) else "failed",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "table": store.table_name,
        "indexes": store.declared_indexes(),
        "cases": {name: {"status": "passed" if passed else "failed"}
                  for name, passed in cases.items()},
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/m05-run.json").write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
