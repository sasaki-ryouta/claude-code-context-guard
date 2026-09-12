# Migration notes

These notes intentionally contain task-relevant details without survival tokens.

- legacy-A already delegates to the canonical normalizer.
- legacy-B was added before the canonical normalizer existed and still constructs `Event` directly.
- exporter output keys are consumed by downstream code and must not change.
- routing groups events by tenant, event type, and external identifier.
- cache keys are persisted only for the duration of a process; format compatibility is not externally guaranteed, but identifier identity is.
- payload dictionaries are opaque to normalization except that they must remain dictionaries on output.
- missing required fields should fail rather than be synthesized.
- sorting is allowed for routing groups, but equal keys must remain stable.
- no network calls or package installation are part of this fixture.
