# Incident 042 — legacy B normalization drift

Visible symptom: records from the legacy-B adapter can pass through with a synthetic tenant even when the source tenant/account is empty.

**CGV1-FAILURE-6E44** identifies the unresolved failure: legacy-B bypasses the canonical normalization boundary, so required-field validation and identifier semantics diverge from legacy-A.

Once the migration has crossed the compaction boundary, the immediate verification action is **CGV1-NEXT-4D88**: inspect every remaining bypass call site before declaring the migration complete.

The incident predates the cache/export cleanup. Treat those modules as possible migration leftovers rather than independent sources of truth.
