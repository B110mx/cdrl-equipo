"""Ejecuta los casos comparables M04 y guarda un resultado machine-readable."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixtures.generate_fixtures import EVENTS, generate
from scripts.evidence_support import source_revision
from src.storage_comparison import DuplicateEventError, load_models


def evaluate_model(model):
    normal = model.get_event(EVENTS[0]["event_id"])
    empty = model.events_by_device(
        "sensor-without-events", "2026-09-27T00:00:00Z", "2026-09-27T23:59:59Z")
    inclusive = model.events_by_device(
        "sensor-lab-01", "2026-09-27T10:00:00Z", "2026-09-27T10:10:00Z")
    duplicate_rejected = False
    try:
        model.insert_event(EVENTS[0])
    except DuplicateEventError:
        duplicate_rejected = True
    cases = {
        "normal": {"status": "passed" if normal == EVENTS[0] else "failed",
                   "event_id": EVENTS[0]["event_id"]},
        "limit_empty": {"status": "passed" if empty == [] else "failed", "count": len(empty)},
        "limit_inclusive": {"status": "passed" if len(inclusive) == 3 else "failed",
                            "count": len(inclusive)},
        "declared_failure_duplicate": {
            "status": "passed" if duplicate_rejected else "failed",
            "expected_error": "DuplicateEventError",
        },
    }
    return {"status": "passed" if all(case["status"] == "passed" for case in cases.values())
            else "failed", "cases": cases}


def main():
    generate()
    stores = {family: evaluate_model(model)
              for family, model in load_models(ROOT / "fixtures").items()}
    report = {
        "module": "m04-storage-comparison",
        "status": "passed" if all(item["status"] == "passed" for item in stores.values())
        else "failed",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture_count": len(EVENTS),
        "stores": stores,
        "weighted_decision": {
            "selected": "document-dynamodb",
            "scores": {"document-dynamodb": 4.20, "object-s3": 3.55,
                       "column-keyspaces": 3.40, "graph-neptune": 2.95},
            "adr": "docs/ADR-003-seleccion-almacenamiento-eventos.md",
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/m04-run.json").write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
