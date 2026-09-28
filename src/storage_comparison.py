"""Adaptadores deterministas para comparar familias de almacenamiento en M04."""
import csv
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path


class DuplicateEventError(ValueError):
    """El contrato de idempotencia rechaza un event_id ya almacenado."""


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class StoreModel:
    family = "base"

    def __init__(self, events):
        self._events = {event["event_id"]: deepcopy(event) for event in events}

    def get_event(self, event_id):
        value = self._events.get(event_id)
        return deepcopy(value) if value else None

    def events_by_device(self, device_id, start, end):
        selected = [event for event in self._events.values()
                    if event["device_id"] == device_id and
                    _instant(start) <= _instant(event["recorded_at"]) <= _instant(end)]
        return sorted((deepcopy(event) for event in selected),
                      key=lambda event: (event["recorded_at"], event["event_id"]))

    def insert_event(self, event):
        if event["event_id"] in self._events:
            raise DuplicateEventError("event_id duplicado")
        self._events[event["event_id"]] = deepcopy(event)


class DocumentStoreModel(StoreModel):
    family = "document"


class GraphStoreModel(StoreModel):
    family = "graph"


class ColumnStoreModel(StoreModel):
    family = "column"


class ObjectStoreModel(StoreModel):
    family = "object"


def load_models(fixtures_dir):
    fixtures_dir = Path(fixtures_dir)
    documents = json.loads((fixtures_dir / "document_data.json").read_text(encoding="utf-8"))
    graph = json.loads((fixtures_dir / "graph_data.json").read_text(encoding="utf-8"))
    graph_events = [node["event"] for node in graph["nodes"] if node["label"] == "Event"]

    with (fixtures_dir / "column_data.csv").open(encoding="utf-8", newline="") as source:
        column_events = []
        for row in csv.DictReader(source):
            row["value"] = float(row["value"])
            row["metadata"] = json.loads(row["metadata"])
            column_events.append(row)

    object_events = []
    with (fixtures_dir / "object_data.jsonl").open(encoding="utf-8") as source:
        for line in source:
            object_events.append(json.loads(line)["event"])

    return {
        "document": DocumentStoreModel(documents),
        "graph": GraphStoreModel(graph_events),
        "column": ColumnStoreModel(column_events),
        "object": ObjectStoreModel(object_events),
    }
