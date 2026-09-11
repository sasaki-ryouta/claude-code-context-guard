# Changelog

## 0.1.2 — target-project safety

- Make `doctor` fail when Context Guard runtime artifacts are not ignored by Git or are already tracked.
- Document target-repository `.gitignore` requirements and prefer `settings.local.json` for machine-local absolute hook paths.
- Make Git-root fallback use a lightweight `rev-parse` instead of a full status collection.
- Keep current CI actions SHA-pinned and maintain the live lifecycle validation runbook.

## 0.1.1 — operational hardening

- Resolve Context Guard state from a stable project root instead of mutable hook `cwd`.
- Preserve immutable per-compaction checkpoint/summary archives while retaining latest-view files.
- Add compaction sequence and hook duration telemetry.
- Make `doctor` validate actual event/matcher/command wiring and require WORKING_STATE.
- Clarify that WORKING_STATE snapshots and native compact summaries are stored verbatim and are not secret-redacted.
- Add Linux CI for Python 3.11, 3.12, and 3.13.

No retrieval, embedding, database, LLM summarization, or automatic semantic-compaction behavior is part of the operational baseline.
