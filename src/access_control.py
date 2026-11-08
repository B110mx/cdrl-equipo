"""Matriz de acceso, fachada documental y eventos de auditoría sin payload."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


POLICY_PATH = Path(__file__).with_name("access-control-policy.json")
ACTION_NAMES = frozenset({
    "read", "write", "administer", "query_audit", "append_audit",
})
RESULTS = frozenset({"succeeded", "failed", "denied"})
ACTOR_PATTERN = re.compile(r"^(?:role|service):[a-z][a-z0-9_-]{0,62}$")
RESOURCE_PATTERN = re.compile(r"^(?:events|audit):[A-Za-z0-9_.-]{1,128}$")


class AccessControlError(RuntimeError):
    """Error base del control de acceso."""


class AccessDeniedError(AccessControlError, PermissionError):
    """La operación fue denegada por la matriz de permisos."""

    def __init__(self, audit_event):
        super().__init__("operation denied by collection access policy")
        self.code = "ACCESS_DENIED"
        self.audit_event = audit_event


def load_policy():
    """Carga la matriz declarativa versionada que también alimenta IAM."""
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def make_audit_event(actor, action, resource, result, occurred_at=None):
    """Construye exclusivamente los cinco campos permitidos por el contrato."""
    if not isinstance(actor, str) or not ACTOR_PATTERN.fullmatch(actor):
        raise ValueError("actor must be a non-sensitive technical identifier")
    if action not in ACTION_NAMES:
        raise ValueError("unsupported audit action")
    if not isinstance(resource, str) or not RESOURCE_PATTERN.fullmatch(resource):
        raise ValueError("resource must be a collection and technical identifier")
    if result not in RESULTS:
        raise ValueError("unsupported audit result")

    instant = occurred_at or datetime.now(timezone.utc).isoformat()
    parsed = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("occurred_at must include a timezone")
    occurred_at = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "actor": actor,
        "action": action,
        "resource": resource,
        "result": result,
        "occurred_at": occurred_at,
    }


def validate_audit_event(event):
    """Valida eventos entrantes sin aceptar campos de payload adicionales."""
    required = {"actor", "action", "resource", "result", "occurred_at"}
    if not isinstance(event, dict) or set(event) != required:
        raise ValueError("audit event must contain only the five contract fields")
    return make_audit_event(**event)


class CollectionAccessController:
    """Evalúa operaciones contra la matriz y construye auditoría mínima."""

    def __init__(self, policy=None):
        self.policy = policy or load_policy()

    def allows(self, role, collection, operation):
        if operation not in self.policy["operations"]:
            raise ValueError("unsupported collection operation")
        permissions = self.policy["roles"].get(role)
        if permissions is None:
            return False
        if collection not in self.policy["collections"]:
            raise ValueError("unsupported collection")
        return operation in permissions.get(collection, [])

    def authorize(self, actor, role, collection, operation, resource_id):
        allowed = self.allows(role, collection, operation)
        event = make_audit_event(
            actor=actor,
            action=operation,
            resource=f"{collection}:{resource_id}",
            result="succeeded" if allowed else "denied",
        )
        if not allowed:
            raise AccessDeniedError(event)
        return event


class AuthorizedDocumentStore:
    """Aplica permisos antes de delegar operaciones al almacén documental."""

    def __init__(self, store, role, actor, audit_sink):
        if not callable(audit_sink):
            raise TypeError("audit_sink must be a callable durable audit sink")
        self.store = store
        self.role = role
        self.actor = actor
        self.audit_sink = audit_sink
        self.access = CollectionAccessController()

    def _execute(self, collection, action, resource_id, operation):
        try:
            self.access.authorize(
                self.actor, self.role, collection, action, resource_id)
        except AccessDeniedError as error:
            self.audit_sink(error.audit_event)
            raise

        try:
            result = operation()
        except Exception:
            self.audit_sink(make_audit_event(
                self.actor, action, f"{collection}:{resource_id}", "failed"))
            raise
        self.audit_sink(make_audit_event(
            self.actor, action, f"{collection}:{resource_id}", "succeeded"))
        return result

    def get_event(self, event_id):
        return self._execute(
            "events", "read", event_id,
            lambda: self.store.get_event(event_id))

    def events_by_device(self, device_id, start, end):
        return self._execute(
            "events", "read", device_id,
            lambda: self.store.events_by_device(device_id, start, end))

    def paginate_events_by_device(self, device_id, page_size=25, cursor=None,
                                  consistent_read=True):
        return self._execute(
            "events", "read", device_id,
            lambda: self.store.paginate_events_by_device(
                device_id, page_size, cursor, consistent_read))

    def events_by_metric_unit(self, metric, unit, start, end):
        return self._execute(
            "events", "read", f"{metric}-{unit}",
            lambda: self.store.events_by_metric_unit(metric, unit, start, end))

    def create_event(self, event):
        resource_id = (
            event.get("event_id", "new-event")
            if isinstance(event, dict) else "new-event"
        )
        return self._execute(
            "events", "write", resource_id,
            lambda: self.store.create_event(event))

    def put_event_idempotent(self, event):
        resource_id = (
            event.get("event_id", "new-event")
            if isinstance(event, dict) else "new-event"
        )
        return self._execute(
            "events", "write", resource_id,
            lambda: self.store.put_event_idempotent(event))

    def update_event(self, event_id, changes):
        return self._execute(
            "events", "write", event_id,
            lambda: self.store.update_event(event_id, changes))

    def replace_event_document(self, event_id, replacement):
        return self._execute(
            "events", "administer", event_id,
            lambda: self.store.replace_event_document(event_id, replacement))

    def delete_event(self, event_id):
        return self._execute(
            "events", "administer", event_id,
            lambda: self.store.delete_event(event_id))

    def get_audit(self, audit_id):
        return self._execute(
            "audit", "query_audit", audit_id,
            lambda: self.store.get_audit(audit_id))

    def record_audit_event(self, audit_event):
        return self._execute(
            "audit", "append_audit", "record",
            lambda: self.store.record_audit_event(audit_event))
