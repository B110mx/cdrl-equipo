"""Migración compatible y reversible de eventos documentales hacia M07 v3."""

from copy import deepcopy

from src.document_store import (
    DocumentEventStore,
    EventNotFoundError,
    InvalidEventError,
)


TARGET_VERSION = 3
SUPPORTED_VERSIONS = {1, 2, TARGET_VERSION}
QUALITY_VALUES = {"good", "uncertain", "unknown"}
DEFAULT_QUALITY = "unknown"


def document_version(document):
    """Interpreta documentos sin marcador como v1 y valida el marcador."""
    version = document.get("schema_version", 1)
    if type(version) is not int or version not in SUPPORTED_VERSIONS:
        raise InvalidEventError(f"unsupported document schema_version: {version!r}")
    return version


def convert_to_v3(document, default_quality=DEFAULT_QUALITY):
    """Convierte v1/v2 a v3; repetir sobre v3 devuelve el mismo documento."""
    if default_quality not in QUALITY_VALUES:
        raise InvalidEventError(f"unsupported quality value: {default_quality!r}")
    converted = deepcopy(document)
    version = document_version(converted)
    if version == TARGET_VERSION:
        return converted
    converted["schema_version"] = TARGET_VERSION
    converted["quality"] = default_quality
    return converted


def rollback_v3(document, target_version):
    """Retira campos v3 y restaura el marcador v1 o v2 solicitado."""
    if target_version not in {1, 2}:
        raise InvalidEventError(
            f"rollback target must be 1 or 2, got {target_version!r}")
    restored = deepcopy(document)
    current_version = document_version(restored)
    if current_version == target_version:
        return restored
    if current_version != TARGET_VERSION:
        raise InvalidEventError(
            f"cannot rollback schema v{current_version} to v{target_version}")
    restored.pop("quality", None)
    if target_version == 1:
        restored.pop("schema_version", None)
    else:
        restored["schema_version"] = 2
    return restored


class DocumentMigrator:
    """Orquesta migración y rollback sin cambiar la identidad del evento."""

    def __init__(self, store=None):
        self.store = store or DocumentEventStore()

    def migrate_event(self, event_id, default_quality=DEFAULT_QUALITY):
        existing = self.store.get_event(event_id)
        if existing is None:
            raise EventNotFoundError(f"event not found: {event_id}")
        from_version = document_version(existing)
        converted = convert_to_v3(existing, default_quality=default_quality)
        if from_version == TARGET_VERSION:
            validated = self.store.validate(converted)
            return {
                "changed": False,
                "from_version": TARGET_VERSION,
                "to_version": TARGET_VERSION,
                "event": validated,
            }
        stored = self.store.replace_event_document(event_id, converted)
        return {
            "changed": True,
            "from_version": from_version,
            "to_version": TARGET_VERSION,
            "event": stored,
        }

    def rollback_event(self, event_id, target_version):
        existing = self.store.get_event(event_id)
        if existing is None:
            raise EventNotFoundError(f"event not found: {event_id}")
        from_version = document_version(existing)
        restored = rollback_v3(existing, target_version=target_version)
        if from_version == target_version:
            validated = self.store.validate(restored)
            return {
                "changed": False,
                "from_version": target_version,
                "to_version": target_version,
                "event": validated,
            }
        stored = self.store.replace_event_document(event_id, restored)
        return {
            "changed": True,
            "from_version": from_version,
            "to_version": target_version,
            "event": stored,
        }
