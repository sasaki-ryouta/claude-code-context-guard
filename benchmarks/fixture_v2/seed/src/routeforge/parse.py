from __future__ import annotations

from collections.abc import Mapping

from .model import Event
from .normalize import normalize_event


def parse_legacy_a(record: Mapping[str, object]) -> Event:
    return normalize_event(
        {
            "tenant_id": record.get("tenant"),
            "external_id": record.get("id"),
            "event_type": record.get("type"),
            "payload": record.get("payload", {}),
        }
    )


def parse_legacy_b(record: Mapping[str, object]) -> Event:
    # This path predates the canonical normalizer and is the incomplete part
    # of the migration. The benchmark task is expected to remove this drift.
    tenant_id = str(record.get("account") or "default").strip()
    external_id = str(record.get("id") or "").strip().lower()
    event_type = str(record.get("kind") or "").strip().lower()
    payload_value = record.get("payload")
    payload = dict(payload_value) if isinstance(payload_value, Mapping) else {}
    return Event(
        tenant_id=tenant_id,
        external_id=external_id,
        event_type=event_type,
        payload=payload,
    )
