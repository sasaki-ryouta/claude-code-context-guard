from __future__ import annotations

from .model import Event


def cache_key(event: Event) -> str:
    # Legacy behavior from before external identifiers became opaque.
    return f"{event.tenant_id}|{event.external_id.lower()}|{event.event_type}"
