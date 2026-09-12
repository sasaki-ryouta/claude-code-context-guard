from __future__ import annotations

from collections.abc import Iterable

from .model import Event


def routing_key(event: Event) -> tuple[str, str, str]:
    return (event.tenant_id, event.event_type, event.external_id)


def route_events(events: Iterable[Event]) -> list[Event]:
    # The timestamp tie-breaker is a legacy artifact. It changes the original
    # order of events that have the same routing key.
    return sorted(
        events,
        key=lambda event: (
            routing_key(event),
            int(event.payload.get("timestamp", 0)),
        ),
    )
