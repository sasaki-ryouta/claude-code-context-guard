from __future__ import annotations

from collections.abc import Mapping

from .model import Event


def _required_text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if value is None:
        raise ValueError(f"missing required field: {key}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"empty required field: {key}")
    return text


def normalize_event(record: Mapping[str, object]) -> Event:
    tenant_id = _required_text(record, "tenant_id")
    external_id = _required_text(record, "external_id")
    event_type = _required_text(record, "event_type").lower()
    payload_value = record.get("payload")
    payload = dict(payload_value) if isinstance(payload_value, Mapping) else {}
    return Event(
        tenant_id=tenant_id,
        external_id=external_id,
        event_type=event_type,
        payload=payload,
    )
