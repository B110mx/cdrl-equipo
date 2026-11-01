"""Benchmark reproducible: página limitada frente a materialización completa."""

import json
import math
import os
import platform
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evidence_support import source_revision
from src.document_store import DocumentEventStore


DEVICE_ID = "sensor-m08-benchmark"
NAMESPACE = uuid.UUID("89fbe82c-ddad-4f4a-9895-650f5f8360c7")


def positive_integer(name, default, minimum=1):
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def percentile_nearest_rank(samples, percentile):
    ordered = sorted(samples)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def batches(values, size=25):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def write_requests(client, table_name, requests):
    pending = requests
    while pending:
        response = client.batch_write_item(
            RequestItems={table_name: pending})
        pending = response.get("UnprocessedItems", {}).get(table_name, [])


def replace_dataset(store, event_count):
    keys = []
    start_key = None
    while True:
        request = {
            "TableName": store.table_name,
            "KeyConditionExpression": "device_id = :device_id",
            "ExpressionAttributeValues": {":device_id": {"S": DEVICE_ID}},
            "ProjectionExpression": "device_id, recorded_at_event_id",
        }
        if start_key:
            request["ExclusiveStartKey"] = start_key
        response = store.client.query(**request)
        keys.extend(response.get("Items", []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            break
    for group in batches([
            {"DeleteRequest": {"Key": key}} for key in keys]):
        write_requests(store.client, store.table_name, group)

    start = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    puts = []
    for index in range(event_count):
        event = {
            "schema_version": 3,
            "event_id": str(uuid.uuid5(NAMESPACE, str(index))),
            "device_id": DEVICE_ID,
            "recorded_at": (
                start + timedelta(seconds=index)).isoformat().replace(
                    "+00:00", "Z"),
            "metric": "temperature",
            "value": 20 + index % 10,
            "unit": "celsius",
            "quality": "good",
            "metadata": {"source": "synthetic-m08-benchmark"},
        }
        stored = store._stored_item(store.validate(event))
        puts.append({"PutRequest": {"Item": store._serialize_item(stored)}})
    for group in batches(puts):
        write_requests(store.client, store.table_name, group)


def baseline_page(store, page_size):
    raw_items = []
    start_key = None
    while True:
        request = {
            "TableName": store.table_name,
            "KeyConditionExpression": "device_id = :device_id",
            "ExpressionAttributeValues": {":device_id": {"S": DEVICE_ID}},
            "ConsistentRead": True,
        }
        if start_key:
            request["ExclusiveStartKey"] = start_key
        response = store.client.query(**request)
        raw_items.extend(response.get("Items", []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            break
    items = [store._deserialize_item(item) for item in raw_items]
    return items[:page_size], len(items)


def optimized_page(store, page_size):
    response = store.paginate_events_by_device(
        DEVICE_ID, page_size=page_size, consistent_read=True)
    return response["items"], len(response["items"])


def measure(operation, repetitions):
    durations = []
    result = None
    read_count = None
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        result, read_count = operation()
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
    return result, read_count, durations


def summary(samples):
    return {
        "unit": "milliseconds",
        "p50": round(percentile_nearest_rank(samples, 0.50), 6),
        "p95": round(percentile_nearest_rank(samples, 0.95), 6),
        "minimum": round(min(samples), 6),
        "maximum": round(max(samples), 6),
    }


def main():
    event_count = positive_integer("M08_BENCHMARK_EVENTS", 240)
    repetitions = positive_integer("M08_BENCHMARK_REPETITIONS", 40)
    warmup = positive_integer("M08_BENCHMARK_WARMUP", 5, minimum=0)
    page_size = positive_integer("M08_PAGE_SIZE", 25)
    if page_size > 100 or page_size > event_count:
        raise ValueError("M08_PAGE_SIZE must be <= 100 and <= dataset size")

    store = DocumentEventStore()
    replace_dataset(store, event_count)
    for _ in range(warmup):
        baseline_page(store, page_size)
        optimized_page(store, page_size)

    baseline_items, baseline_read, baseline_samples = measure(
        lambda: baseline_page(store, page_size), repetitions)
    optimized_items, optimized_read, optimized_samples = measure(
        lambda: optimized_page(store, page_size), repetitions)
    baseline_ids = [item["event_id"] for item in baseline_items]
    optimized_ids = [item["event_id"] for item in optimized_items]
    equivalent = baseline_ids == optimized_ids
    baseline_stats = summary(baseline_samples)
    optimized_stats = summary(optimized_samples)
    ratio = (baseline_stats["p50"] / optimized_stats["p50"]
             if optimized_stats["p50"] else None)

    endpoint = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")
    report = {
        "module": "m08-document-query-benchmark",
        "status": "passed" if equivalent else "failed",
        "technical_author": "Luis Bryan Rojas Rodriguez",
        **source_revision(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "backend": "dynamodb-local" if endpoint else "aws-dynamodb",
            "region": os.getenv("AWS_REGION", "us-east-1"),
            "table": store.table_name,
        },
        "method": {
            "clock": "time.perf_counter_ns",
            "percentile": "nearest-rank",
            "warmup_runs_excluded": warmup,
            "measured_repetitions_per_variant": repetitions,
            "dataset_events": event_count,
            "page_size": page_size,
            "fixture_kind": "deterministic-synthetic",
        },
        "baseline": {
            "description": "query completo de la partición y recorte en cliente",
            "items_materialized_per_run": baseline_read,
            **baseline_stats,
        },
        "optimized": {
            "description": "query con Limit y cursor sobre la clave primaria",
            "items_returned_per_run": optimized_read,
            **optimized_stats,
        },
        "comparison": {
            "same_first_page": equivalent,
            "p50_baseline_over_optimized": (
                round(ratio, 6) if ratio is not None else None),
            "trade_off": (
                "Limit reduce datos materializados y habilita continuación; "
                "el cursor no ofrece una instantánea ante escrituras concurrentes."),
            "claim": (
                "Resultado observado en este entorno; no se generaliza a producción."),
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/m08-benchmark.json").write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
