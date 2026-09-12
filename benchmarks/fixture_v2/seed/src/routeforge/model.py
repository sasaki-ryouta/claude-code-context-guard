from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    tenant_id: str
    external_id: str
    event_type: str
    payload: dict[str, object]
