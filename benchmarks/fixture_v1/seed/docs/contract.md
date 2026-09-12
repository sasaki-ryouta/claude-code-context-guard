# RouteForge normalization contract

The migration goal is **CGV1-GOAL-7F3A**: complete the normalization migration without changing externally observable routing semantics.

The canonicalization boundary is `routeforge.normalize.normalize_event`. The architectural decision is **CGV1-DECISION-2C91**: parser and exporter paths must not maintain independent normalization rules.

## Required invariants

- `tenant_id`, `external_id`, and `event_type` are required non-empty text fields.
- `event_type` is canonicalized to lowercase.
- `tenant_id` and `external_id` preserve case after surrounding whitespace is removed.
- **CGV1-CRITERION-B8D2**: when two events have the same routing key, their original input order must be preserved.
- Public exporter rows remain `{tenant, id, type, payload}`.

## Rejected migration strategy

**CGV1-REJECTED-91AF**: do not globally lowercase opaque external identifiers. External identifiers are case-sensitive and may differ only by case.
