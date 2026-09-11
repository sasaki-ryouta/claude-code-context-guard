# Changelog

## 0.1.1 — operational hardening

- Resolve Context Guard state from a stable project root instead of mutable hook `cwd`.
- Preserve immutable per-compaction checkpoint/summary archives while retaining latest-view files.
- Add compaction sequence and hook duration telemetry.
- Make `doctor` validate actual event/matcher/command wiring and require WORKING_STATE.
- Clarify that WORKING_STATE snapshots and native compact summaries are stored verbatim and are not secret-redacted.
- Add Linux CI for Python 3.11, 3.12, and 3.13.

No retrieval, embedding, database, LLM summarization, or automatic semantic-compaction behavior was added.
