"""Valida fixtures e inicializa las tablas e índices de DynamoDB de forma repetible."""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
EVENTS_TABLE = os.getenv("DYNAMODB_EVENTS_TABLE", "cdrl-events")
DEVICES_TABLE = os.getenv("DYNAMODB_DEVICES_TABLE", "cdrl-devices")
REGION = os.getenv("AWS_REGION", "us-east-1")
ENDPOINT = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000") or None
SCHEMA_PATH = ROOT / "docs" / "M04-event-document-schema.json"
EVENT_INDEXES = {
    "EventIdIndex": ("event_id", None),
    "DeviceMetricTimeIndex": ("device_metric_unit", "recorded_at_event_id"),
}
DEVICE_INDEXES = {"StatusIndex": ("status", "device_id")}


def make_client():
    options = {"region_name": REGION, "endpoint_url": ENDPOINT}
    if ENDPOINT:
        options.update(aws_access_key_id="local", aws_secret_access_key="local")
    return boto3.client("dynamodb", **options)


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

    existing = {index["IndexName"] for index in table.get("GlobalSecondaryIndexes", [])}
    for index_name, (index_partition, index_sort) in indexes.items():
        if index_name not in existing:
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


def seed_events(client, validator):
    resource = boto3.resource(
        "dynamodb", region_name=REGION, endpoint_url=ENDPOINT,
        **({"aws_access_key_id": "local", "aws_secret_access_key": "local"} if ENDPOINT else {}),
    )
    table = resource.Table(EVENTS_TABLE)
    documents = json.loads(
        (ROOT / "fixtures" / "document_data.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    for event in documents:
        event.setdefault("metadata", {})
        validate_event(event, validator)
        item = dict(event)
        item["recorded_at_event_id"] = f"{event['recorded_at']}#{event['event_id']}"
        item["device_metric_unit"] = f"{event['device_id']}#{event['metric']}#{event['unit']}"
        item.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(event_id)")
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


def seed_devices(client):
    resource = boto3.resource(
        "dynamodb", region_name=REGION, endpoint_url=ENDPOINT,
        **({"aws_access_key_id": "local", "aws_secret_access_key": "local"} if ENDPOINT else {}),
    )
    table = resource.Table(DEVICES_TABLE)
    for device_id, status in (
        ("sensor-lab-01", "active"),
        ("sensor-lab-02", "active"),
        ("sensor-lab-03", "inactive"),
    ):
        try:
            table.put_item(
                Item={"device_id": device_id, "status": status},
                ConditionExpression="attribute_not_exists(device_id)",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


def main():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    client = make_client()
    ensure_table(
        client, EVENTS_TABLE, "device_id", "recorded_at_event_id", EVENT_INDEXES)
    ensure_table(client, DEVICES_TABLE, "device_id", None, DEVICE_INDEXES)
    seed_events(client, validator)
    seed_devices(client)
    print("DynamoDB document store initialized; event and device fixtures validated.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Document store initialization failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)