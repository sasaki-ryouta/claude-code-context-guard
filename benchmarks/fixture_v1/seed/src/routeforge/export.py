from __future__ import annotations

from collections.abc import Iterable

from .model import Event


def export_records(events: Iterable[Event]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in events:
        # This exporter still carries normalization logic from the pre-migration
        # implementation and therefore can diverge from the canonical boundary.
        rows.append(
            {
                "tenant": event.tenant_id.strip(),
                "id": event.external_id.strip().lower(),
                "type": event.event_type.strip().lower(),
                "payload": dict(event.payload),
            }
        )
    return rows
