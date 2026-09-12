# RouteForge normalization contract

The migration goal is to complete the normalization migration without changing externally observable routing semantics.

The canonicalization boundary is `routeforge.normalize.normalize_event`. Parser and exporter paths must not maintain independent normalization rules.

## Required invariants

- `tenant_id`, `external_id`, and `event_type` are required non-empty text fields.
- `event_type` is canonicalized to lowercase.
- `tenant_id` and `external_id` preserve case after surrounding whitespace is removed.
- when two events have the same routing key, their original input order must be preserved.
- public exporter rows remain `{tenant, id, type, payload}`.

## Rejected migration strategy

Do not globally lowercase opaque external identifiers. External identifiers are case-sensitive and may differ only by case.
