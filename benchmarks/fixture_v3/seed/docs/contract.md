# RouteForge normalization contract

The migration goal is **CGV2-GOAL-A13C**: complete the normalization migration without changing externally observable routing semantics.

The canonicalization boundary is `routeforge.normalize.normalize_event`. The architectural decision is **CGV2-BOUNDARY-91B7**: parser and exporter paths must not maintain independent normalization rules.

## Required invariants

- `tenant_id`, `external_id`, and `event_type` are required non-empty text fields.
- `event_type` is canonicalized to lowercase.
- **CGV2-IDCASE-3E8A**: `tenant_id` and `external_id` preserve case after surrounding whitespace is removed.
- **CGV2-ORDER-6D2F**: when two events have the same routing key, their original input order must be preserved.
- **CGV2-SCHEMA-C4D1**: public exporter rows remain `{tenant, id, type, payload}`.

## Rejected migration strategy

**CGV2-REJECTED-75F0**: do not globally lowercase opaque external identifiers. External identifiers are case-sensitive and may differ only by case.
