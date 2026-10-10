"""Valida fixtures e inicializa DynamoDB sin migrar los documentos existentes.

La ausencia de schema_version identifica v1; los documentos nuevos declaran v2.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError
from dotenv import load_dotenv
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
EVENTS_TABLE = os.getenv("DYNAMODB_EVENTS_TABLE", "cdrl-events")
DEVICES_TABLE = os.getenv("DYNAMODB_DEVICES_TABLE", "cdrl-devices")
AUDIT_TABLE = os.getenv("DYNAMODB_AUDIT_TABLE", "cdrl-audit")
REGION = os.getenv("AWS_REGION", "us-east-1")
ENDPOINT = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000") or None
SCHEMA_PATHS = {
    1: ROOT / "docs" / "M05-event-document-schema.json",
    2: ROOT / "docs" / "M06-event-document-schema-v2.json",
}
EVENT_INDEXES = {
    "EventIdIndex": ("event_id", None),
    "DeviceMetricTimeIndex": ("device_metric_unit", "recorded_at_event_id"),
    "MetricUnitTimeIndex": ("metric_unit", "recorded_at_event_id"),
}
DEVICE_INDEXES = {"StatusIndex": ("status", "device_id")}
AUDIT_INDEXES = {"EventTimeIndex": ("event_id", "occurred_at_audit_id")}


def make_client():
    options = {"region_name": REGION, "endpoint_url": ENDPOINT}
    if ENDPOINT:
        options.update(aws_access_key_id="local", aws_secret_access_key="local")
    return boto3.client("dynamodb", **options)


def wait_for_endpoint(client):
    if not ENDPOINT:
        return
    for attempt in range(30):
        try:
            client.list_tables(Limit=1)
            return
        except EndpointConnectionError:
            if attempt == 29:
                raise
            time.sleep(1)


def index_definition(name, partition_key, sort_key=None):
    keys = [{"AttributeName": partition_key, "KeyType": "HASH"}]
    if sort_key:
        keys.append({"AttributeName": sort_key, "KeyType": "RANGE"})
    return {
        "IndexName": name,
        "KeySchema": keys,
        "Projection": {"ProjectionType": "ALL"},
    }


def ensure_table(client, name, partition_key, sort_key, indexes):
    definitions = {partition_key}
    if sort_key:
        definitions.add(sort_key)
    for index_partition, index_sort in indexes.values():
        definitions.add(index_partition)
        if index_sort:
            definitions.add(index_sort)
    attributes = [{"AttributeName": key, "AttributeType": "S"} for key in sorted(definitions)]
    key_schema = [{"AttributeName": partition_key, "KeyType": "HASH"}]
    if sort_key:
        key_schema.append({"AttributeName": sort_key, "KeyType": "RANGE"})

    try:
        table = client.describe_table(TableName=name)["Table"]
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        client.create_table(
            TableName=name,
            AttributeDefinitions=attributes,
            KeySchema=key_schema,
            BillingMode="PAY_PER_REQUEST",
            GlobalSecondaryIndexes=[
                index_definition(index_name, index_partition, index_sort)
                for index_name, (index_partition, index_sort) in indexes.items()
            ],
        )
        client.get_waiter("table_exists").wait(TableName=name)
        table = client.describe_table(TableName=name)["Table"]

    expected_keys = {"HASH": partition_key}
    if sort_key:
        expected_keys["RANGE"] = sort_key
    actual_keys = {
        key["KeyType"]: key["AttributeName"]
        for key in table["KeySchema"]
    }
    if actual_keys != expected_keys:
        raise ValueError(f"table {name} has an incompatible primary key")

    existing = {index["IndexName"] for index in table.get("GlobalSecondaryIndexes", [])}
    for index_name, (index_partition, index_sort) in indexes.items():
        if index_name in existing:
            actual_index = next(
                index for index in table["GlobalSecondaryIndexes"]
                if index["IndexName"] == index_name
            )
            actual_index_keys = {
                key["KeyType"]: key["AttributeName"]
                for key in actual_index["KeySchema"]
            }
            expected_index_keys = {"HASH": index_partition}
            if index_sort:
                expected_index_keys["RANGE"] = index_sort
            if actual_index_keys != expected_index_keys:
                raise ValueError(f"index {index_name} on table {name} is incompatible")
            continue
        client.update_table(
            TableName=name,
            AttributeDefinitions=[
                {"AttributeName": index_partition, "AttributeType": "S"},
                *([{"AttributeName": index_sort, "AttributeType": "S"}] if index_sort else []),
            ],
            GlobalSecondaryIndexUpdates=[{
                "Create": index_definition(index_name, index_partition, index_sort)
            }],
        )
        wait_for_active(client, name)
    wait_for_active(client, name)


def wait_for_active(client, name):
    for _ in range(60):
        table = client.describe_table(TableName=name)["Table"]
        indexes_active = all(
            index.get("IndexStatus") == "ACTIVE"
            for index in table.get("GlobalSecondaryIndexes", [])
        )
        if table["TableStatus"] == "ACTIVE" and indexes_active:
            return
        time.sleep(1)
    raise TimeoutError(f"DynamoDB table did not become active: {name}")


def validate_event(event, validator):
    validator.validate(event)
    recorded_at = datetime.fromisoformat(event["recorded_at"].replace("Z", "+00:00"))
    if recorded_at.utcoffset() is None or recorded_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("recorded_at must include a timezone and be no more than five minutes ahead")
    if len(json.dumps(event.get("metadata", {}), ensure_ascii=False).encode("utf-8")) > 2048:
        raise ValueError("metadata exceeds 2048 bytes")
    if "ingested_at" in event:
        ingested_at = datetime.fromisoformat(event["ingested_at"].replace("Z", "+00:00"))
        if ingested_at.utcoffset() is None:
            raise ValueError("ingested_at must include a timezone")


def seed_events(client, validators):
    sys.path.insert(0, str(ROOT))
    from src.document_store import DocumentEventStore

    fixture_paths = (
        ROOT / "fixtures" / "document_data.json",
        ROOT / "fixtures" / "m06-document-data-v2.json",
    )
    documents = [
        event
        for path in fixture_paths
        for event in json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    ]
    for event in documents:
        event.setdefault("metadata", {})
        version = event.get("schema_version", 1)
        if type(version) is not int or version not in validators:
            raise ValueError(f"unsupported document schema_version: {version!r}")
        validator = validators[version]
        validate_event(event, validator)
        store = DocumentEventStore(
            client=client, table_name=EVENTS_TABLE,
            schema_path=SCHEMA_PATHS[version])
        store.put_event_idempotent(event)


def seed_devices(client):
    for device_id, status in (
        ("sensor-lab-01", "active"),
        ("sensor-lab-02", "active"),
        ("sensor-lab-03", "inactive"),
    ):
        try:
            client.put_item(
                TableName=DEVICES_TABLE,
                Item={
                    "device_id": {"S": device_id},
                    "status": {"S": status},
                },
                ConditionExpression="attribute_not_exists(device_id)",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


def main():
    validators = {}
    for version, path in SCHEMA_PATHS.items():
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validators[version] = Draft202012Validator(
            schema, format_checker=FormatChecker())
    client = make_client()
    wait_for_endpoint(client)
    ensure_table(
        client, EVENTS_TABLE, "device_id", "recorded_at_event_id", EVENT_INDEXES)
    ensure_table(client, DEVICES_TABLE, "device_id", None, DEVICE_INDEXES)
    ensure_table(client, AUDIT_TABLE, "audit_id", None, AUDIT_INDEXES)
    seed_events(client, validators)
    seed_devices(client)
    print(
        "DynamoDB initialized with event schemas v1/v2 and audit table; "
        "event and device fixtures validated."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Document store initialization failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
