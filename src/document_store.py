"""CRUD versionado, auditoría y recuperación para eventos en DynamoDB."""

import json
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class DocumentStoreError(RuntimeError):
    """Error base del almacén documental."""


class InvalidEventError(DocumentStoreError):
    """El documento no satisface el contrato de telemetría."""


class DuplicateEventError(DocumentStoreError):
    """El event_id ya pertenece a otro documento."""


class EventNotFoundError(DocumentStoreError):
    """No existe el evento solicitado."""


class DataIntegrityError(DocumentStoreError):
    """El índice devolvió más de un documento para un event_id único."""


def _to_decimal(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_decimal(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_decimal(item) for key, item in value.items()}
    return value


def _to_plain(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


def _normalize_timestamp(value):
    """Devuelve un instante ISO 8601 canónico en UTC para claves ordenables."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class DocumentEventStore:
    """Acceso a DynamoDB usando las claves e índices declarados por M05."""

    immutable_fields = {"event_id", "device_id", "recorded_at", "ingested_at"}

    def __init__(self, client=None, table_name=None, schema_path=None,
                 schema_paths=None, audit_table_name=None):
        endpoint = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000") or None
        region = os.getenv("AWS_REGION", "us-east-1")
        options = {"region_name": region, "endpoint_url": endpoint}
        if endpoint:
            options.update(aws_access_key_id="local", aws_secret_access_key="local")
        self.client = client or boto3.client("dynamodb", **options)
        self.table_name = table_name or os.getenv("DYNAMODB_EVENTS_TABLE", "cdrl-events")
        self.audit_table_name = audit_table_name or os.getenv(
            "DYNAMODB_AUDIT_TABLE", "cdrl-audit")
        if schema_path is not None:
            selected_path = Path(schema_path)
            selected_schema = json.loads(
                selected_path.read_text(encoding="utf-8"))
            declared_version = (
                selected_schema.get("properties", {})
                .get("schema_version", {})
                .get("const", 1)
            )
            selected_schemas = {declared_version: selected_schema}
        else:
            selected_paths = schema_paths or {
                1: ROOT / "docs" / "M05-event-document-schema.json",
                2: ROOT / "docs" / "M06-event-document-schema-v2.json",
                3: ROOT / "docs" / "M07-event-document-schema-v3.json",
            }
            selected_schemas = {
                version: json.loads(
                    Path(selected_path).read_text(encoding="utf-8"))
                for version, selected_path in selected_paths.items()
            }
        self.validators = {}
        for version, schema in selected_schemas.items():
            self.validators[version] = Draft202012Validator(
                schema, format_checker=FormatChecker())
        self.validator = self.validators[min(self.validators)]
        self.serializer = TypeSerializer()
        self.deserializer = TypeDeserializer()

    def validate(self, event):
        document = deepcopy(event)
        document.setdefault("metadata", {})
        try:
            version = document.get("schema_version", 1)
            if type(version) is not int or version not in self.validators:
                raise ValueError(f"unsupported document schema_version: {version!r}")
            self.validators[version].validate(document)
            recorded_at = datetime.fromisoformat(
                document["recorded_at"].replace("Z", "+00:00"))
            if recorded_at.utcoffset() is None:
                raise ValueError("recorded_at must include a timezone")
            if recorded_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("recorded_at must be no more than five minutes ahead")
            document["recorded_at"] = _normalize_timestamp(document["recorded_at"])
            metadata_size = len(json.dumps(
                document["metadata"], ensure_ascii=False).encode("utf-8"))
            if metadata_size > 2048:
                raise ValueError("metadata exceeds 2048 bytes")
            if "ingested_at" in document:
                ingested_at = datetime.fromisoformat(
                    document["ingested_at"].replace("Z", "+00:00"))
                if ingested_at.utcoffset() is None:
                    raise ValueError("ingested_at must include a timezone")
                document["ingested_at"] = _normalize_timestamp(
                    document["ingested_at"])
        except (ValidationError, ValueError, TypeError, KeyError) as error:
            raise InvalidEventError(str(error)) from error
        return document

    def record_audit(self, event_id, operation, changed_fields, outcome="succeeded",
                     audit_id=None, occurred_at=None):
        """Registra metadatos de una operación sin copiar valores ni secretos."""
        timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
        identifier = audit_id or f"{operation}#{event_id}#{timestamp}"
        record = {
            "audit_id": identifier,
            "event_id": event_id,
            "occurred_at": timestamp,
            "occurred_at_audit_id": f"{timestamp}#{identifier}",
            "operation": operation,
            "outcome": outcome,
            "changed_fields": sorted(set(changed_fields)),
        }
        self.client.put_item(
            TableName=self.audit_table_name,
            Item=self._serialize_item(record),
        )
        return _to_plain(record)

    def get_audit(self, audit_id):
        response = self.client.get_item(
            TableName=self.audit_table_name,
            Key={"audit_id": {"S": audit_id}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        return self._deserialize_item(item) if item else None

    def update_event_audited(self, event_id, changes, audit_id=None):
        """Actualiza un evento y deja una traza sin valores del documento."""
        updated = self.update_event(event_id, changes)
        audit = self.record_audit(
            event_id=event_id,
            operation="update_event",
            changed_fields=changes.keys(),
            audit_id=audit_id,
        )
        return {"event": updated, "audit": audit}

    def _serialize_item(self, item):
        return {key: self.serializer.serialize(value)
                for key, value in _to_decimal(item).items()}

    def _deserialize_item(self, item):
        document = {key: self.deserializer.deserialize(value)
                    for key, value in item.items()}
        for internal in (
            "recorded_at_event_id", "device_metric_unit", "metric_unit", "_record_type"):
            document.pop(internal, None)
        return _to_plain(document)

    @staticmethod
    def _lock_key(event_id):
        return {
            "device_id": f"__event_id__#{event_id}",
            "recorded_at_event_id": "UNIQUE",
        }

    def _stored_item(self, event):
        item = deepcopy(event)
        item.setdefault("metadata", {})
        item.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())
        item["recorded_at_event_id"] = f"{item['recorded_at']}#{item['event_id']}"
        item["device_metric_unit"] = (
            f"{item['device_id']}#{item['metric']}#{item['unit']}")
        item["metric_unit"] = f"{item['metric']}#{item['unit']}"
        item["_record_type"] = "event"
        return item

    def create_event(self, event):
        """Crea un evento y reserva event_id de forma atómica y global."""
        document = self.validate(event)
        stored = self._stored_item(document)
        lock = {**self._lock_key(document["event_id"]), "_record_type": "event_id_lock"}
        try:
            self.client.transact_write_items(TransactItems=[
                {"Put": {
                    "TableName": self.table_name,
                    "Item": self._serialize_item(lock),
                    "ConditionExpression": "attribute_not_exists(device_id)",
                }},
                {"Put": {
                    "TableName": self.table_name,
                    "Item": self._serialize_item(stored),
                    "ConditionExpression": (
                        "attribute_not_exists(device_id) AND "
                        "attribute_not_exists(recorded_at_event_id)"),
                }},
            ])
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise DuplicateEventError(
                    f"event_id already exists: {document['event_id']}") from error
            raise
        return self._deserialize_item(self._serialize_item(stored))

    def put_event_idempotent(self, event):
        """Inserta una vez; repetir el mismo documento no lo duplica."""
        document = self.validate(event)
        existing = self.get_event(document["event_id"])
        if existing is not None:
            comparable = deepcopy(existing)
            comparable.pop("ingested_at", None)
            expected = deepcopy(document)
            expected.pop("ingested_at", None)
            if comparable == expected:
                self._ensure_lock(document["event_id"])
                return {"created": False, "event": existing}
            raise DuplicateEventError(
                f"event_id belongs to a different document: {document['event_id']}")
        try:
            created = self.create_event(document)
        except DuplicateEventError:
            existing = self.get_event(document["event_id"])
            if existing is None:
                raise
            comparable = deepcopy(existing)
            comparable.pop("ingested_at", None)
            expected = deepcopy(document)
            expected.pop("ingested_at", None)
            if comparable != expected:
                raise
            return {"created": False, "event": existing}
        return {"created": True, "event": created}

    def _ensure_lock(self, event_id):
        lock = {**self._lock_key(event_id), "_record_type": "event_id_lock"}
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item=self._serialize_item(lock),
                ConditionExpression="attribute_not_exists(device_id)",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def get_event(self, event_id):
        """Consulta por EventIdIndex; evita un Scan."""
        response = self.client.query(
            TableName=self.table_name,
            IndexName="EventIdIndex",
            KeyConditionExpression="event_id = :event_id",
            ExpressionAttributeValues={":event_id": {"S": event_id}},
            Limit=2,
        )
        items = response.get("Items", [])
        if len(items) > 1:
            raise DataIntegrityError(f"duplicate event_id in index: {event_id}")
        return self._deserialize_item(items[0]) if items else None

    def events_by_device(self, device_id, start, end):
        """Consulta un intervalo inclusivo usando la clave primaria compuesta."""
        start = _normalize_timestamp(start)
        end = _normalize_timestamp(end)
        response = self.client.query(
            TableName=self.table_name,
            KeyConditionExpression=(
                "device_id = :device_id AND "
                "recorded_at_event_id BETWEEN :start AND :end"),
            ExpressionAttributeValues={
                ":device_id": {"S": device_id},
                ":start": {"S": f"{start}#"},
                ":end": {"S": f"{end}#\uffff"},
            },
        )
        return [self._deserialize_item(item) for item in response.get("Items", [])]

    def events_by_metric_unit(self, metric, unit, start, end):
        """Consulta el resumen del ADR mediante MetricUnitTimeIndex."""
        start = _normalize_timestamp(start)
        end = _normalize_timestamp(end)
        response = self.client.query(
            TableName=self.table_name,
            IndexName="MetricUnitTimeIndex",
            KeyConditionExpression=(
                "metric_unit = :metric_unit AND "
                "recorded_at_event_id BETWEEN :start AND :end"),
            ExpressionAttributeValues={
                ":metric_unit": {"S": f"{metric}#{unit}"},
                ":start": {"S": f"{start}#"},
                ":end": {"S": f"{end}#\uffff"},
            },
        )
        return [self._deserialize_item(item) for item in response.get("Items", [])]

    def update_event(self, event_id, changes):
        """Actualiza campos mutables sin cambiar las claves de acceso."""
        forbidden = self.immutable_fields.intersection(changes)
        if forbidden:
            raise InvalidEventError(
                f"immutable fields cannot be updated: {', '.join(sorted(forbidden))}")
        existing = self.get_event(event_id)
        if existing is None:
            raise EventNotFoundError(f"event not found: {event_id}")
        updated = {**existing, **deepcopy(changes)}
        updated = self.validate(updated)
        stored = self._stored_item(updated)
        self.client.put_item(
            TableName=self.table_name,
            Item=self._serialize_item(stored),
            ConditionExpression=(
                "attribute_exists(device_id) AND "
                "attribute_exists(recorded_at_event_id)"),
        )
        return self._deserialize_item(self._serialize_item(stored))

    def replace_event_document(self, event_id, replacement):
        """Reemplaza un documento conservando identidad y claves de acceso.

        La migración de versión necesita agregar o retirar atributos. Un
        reemplazo completo evita que queden campos exclusivos de una versión
        después del rollback, pero nunca permite cambiar la identidad del
        evento ni su instante de ingestión.
        """
        existing = self.get_event(event_id)
        if existing is None:
            raise EventNotFoundError(f"event not found: {event_id}")
        candidate = deepcopy(replacement)
        if candidate.get("event_id") != event_id:
            raise InvalidEventError("replacement event_id does not match")
        for field in self.immutable_fields:
            if candidate.get(field) != existing.get(field):
                raise InvalidEventError(
                    f"immutable field cannot change during replacement: {field}")
        candidate = self.validate(candidate)
        stored = self._stored_item(candidate)
        self.client.put_item(
            TableName=self.table_name,
            Item=self._serialize_item(stored),
            ConditionExpression=(
                "attribute_exists(device_id) AND "
                "attribute_exists(recorded_at_event_id)"),
        )
        return self._deserialize_item(self._serialize_item(stored))

    def delete_event(self, event_id):
        """Elimina evento y reserva; repetir la ausencia devuelve False."""
        existing = self.get_event(event_id)
        if existing is None:
            return False
        event_key = {
            "device_id": existing["device_id"],
            "recorded_at_event_id": f"{existing['recorded_at']}#{event_id}",
        }
        self.client.transact_write_items(TransactItems=[
            {"Delete": {
                "TableName": self.table_name,
                "Key": self._serialize_item(event_key),
            }},
            {"Delete": {
                "TableName": self.table_name,
                "Key": self._serialize_item(self._lock_key(event_id)),
            }},
        ])
        return True

    def declared_indexes(self):
        table = self.client.describe_table(TableName=self.table_name)["Table"]
        return sorted(index["IndexName"]
                      for index in table.get("GlobalSecondaryIndexes", []))
