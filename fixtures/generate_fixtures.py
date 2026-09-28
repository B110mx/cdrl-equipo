"""Genera fixtures M04 deterministas para las cuatro familias de almacenamiento."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"

EVENTS = [
    {"event_id": "018f47a0-79f2-7c19-bc7f-1a26d47e9401", "device_id": "sensor-lab-01",
     "recorded_at": "2026-09-27T10:00:00Z", "metric": "temperature", "value": 20.0,
     "unit": "celsius", "metadata": {"source": "synthetic-m04"}},
    {"event_id": "018f47a0-79f2-7c19-bc7f-1a26d47e9402", "device_id": "sensor-lab-01",
     "recorded_at": "2026-09-27T10:05:00Z", "metric": "temperature", "value": -80.0,
     "unit": "celsius", "metadata": {"source": "synthetic-m04", "boundary": "minimum"}},
    {"event_id": "018f47a0-79f2-7c19-bc7f-1a26d47e9403", "device_id": "sensor-lab-01",
     "recorded_at": "2026-09-27T10:10:00Z", "metric": "temperature", "value": 200.0,
     "unit": "celsius", "metadata": {"source": "synthetic-m04", "boundary": "maximum"}},
    {"event_id": "018f47a0-79f2-7c19-bc7f-1a26d47e9404", "device_id": "sensor-lab-02",
     "recorded_at": "2026-09-27T10:15:00Z", "metric": "humidity", "value": 0.0,
     "unit": "percent", "metadata": {"source": "synthetic-m04", "boundary": "minimum"}},
    {"event_id": "018f47a0-79f2-7c19-bc7f-1a26d47e9405", "device_id": "sensor-lab-02",
     "recorded_at": "2026-09-27T10:20:00Z", "metric": "humidity", "value": 100.0,
     "unit": "percent", "metadata": {"source": "synthetic-m04", "boundary": "maximum"}},
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate():
    """Escribe representaciones equivalentes; repetirlo produce los mismos bytes."""
    FIXTURES.mkdir(exist_ok=True)
    write_json(FIXTURES / "document_data.json", EVENTS)
    devices = sorted({event["device_id"] for event in EVENTS})
    graph = {
        "nodes": ([{"id": device, "label": "Device"} for device in devices] +
                  [{"id": event["event_id"], "label": "Event", "event": event}
                   for event in EVENTS]),
        "edges": [{"from": event["device_id"], "to": event["event_id"],
                   "type": "PRODUCED"} for event in EVENTS],
    }
    write_json(FIXTURES / "graph_data.json", graph)

    columns = ["event_id", "device_id", "recorded_at", "metric", "value", "unit", "metadata"]
    with (FIXTURES / "column_data.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for event in EVENTS:
            row = dict(event)
            row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True)
            writer.writerow(row)

    with (FIXTURES / "object_data.jsonl").open("w", newline="", encoding="utf-8") as output:
        for event in EVENTS:
            key = (f"events/{event['device_id']}/{event['recorded_at'][:10]}/"
                   f"{event['event_id']}.json")
            output.write(json.dumps({"key": key, "event": event},
                                    ensure_ascii=False, sort_keys=True) + "\n")
    return EVENTS


if __name__ == "__main__":
    generate()
    print("Fixtures M04 generados: document, graph, column y object store")
