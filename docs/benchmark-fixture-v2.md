---
title: Benchmark fixture v2
date: 2026-09-12
tags: [benchmark, fixture, compaction, v0.2]
status: pre-dry-run
type: experiment-spec
---

# Benchmark fixture v2 — repaired long-distance survival

Issues: #13, #19. H3 outcome sensitivity is separated into #18.

Fixture v1 is frozen as an invalid pilot fixture. Its dry run successfully validated the harness but exposed a measurement contradiction: turn 14 prohibited outputting token strings and the immediately following primary probe required those same strings. v2 repairs measurement validity without using the observed arm ranking to tune for a treatment win.

## 1. Question and scope

Primary question:

> When durable high-value state was established early, has not been reread or echoed recently, and the compaction boundary is fixed, does Context Guard rehydration improve exact state survival relative to state-only/native compaction?

This fixture is for **H1 mechanism isolation**. It is not an H3 task-outcome benchmark. The v1 dry run showed all arms could pass the RouteForge evaluator, so making this same task harder after seeing those outcomes would risk outcome-dependent benchmark tuning. A separately pre-registered outcome-sensitive fixture is tracked in #18.

## 2. Frozen environment

```text
CLAUDE_CODE_VERSION = 2.1.245
MODEL_ID = claude-sonnet-5
FIXED_COMPACT_BOUNDARY = after scripted turn 14
TARGET_INITIAL_COMMIT = 82d14b45a2bc5aa93bb23b901343e2e616464303
AUTO_COMPACTION = disabled with DISABLE_AUTO_COMPACT=1
AUTO_UPDATE = disabled with DISABLE_AUTOUPDATER=1
NETWORK = unnecessary / not allowed
```

The runner verifies the observed Claude Code version before and after each run and aborts on drift. It also aborts when the benchmark checkout has tracked dirty state.

## 3. Why the marker set changed

v1 incorrectly placed two dynamic fields in the exact-survival denominator:

- an unresolved failure that could become resolved before compaction;
- a next action whose semantic meaning changes as phases advance.

Correct working-state hygiene may remove or replace those fields, so scoring their old tokens as mandatory survival would penalize correct behavior.

v2 therefore scores six **durable** facts that remain valid through the fixed boundary:

```text
CGV2-GOAL-A13C       migration goal
CGV2-ORDER-6D2F      stable ordering criterion
CGV2-BOUNDARY-91B7   canonicalization-boundary decision
CGV2-IDCASE-3E8A     identifier-case invariant
CGV2-SCHEMA-C4D1     public output-schema invariant
CGV2-REJECTED-75F0   rejected global-lowercasing strategy
```

Current failure and next action remain part of normal WORKING_STATE operation and task reasoning, but are not part of this fixture's exact long-distance denominator. They should be tested with continuation/behavior metrics rather than stale-token preservation.

## 4. Arm definitions

| arm | WORKING_STATE | Context Guard hooks | purpose |
|---|---|---|---|
| A | no | no | native baseline |
| B | yes | no | explicit-state only |
| C | yes | yes | explicit-state + rehydration treatment |
| D | no | yes | hooks/no-state control |

B and C receive byte-identical state instructions/assets and differ only in hook configuration.

## 5. Protocol

The initial orientation message is **not** a task turn. File/repository/network tools are disabled for it and the expected behavior is a readiness acknowledgement only.

Scripted turns 1–14 retain the v1 task categories. Turn 2 establishes durable state by reading `docs/contract.md` and `docs/incident.md`; turns 3–14 perform task-relevant investigation, implementation, and verification. The fixed `/compact` occurs after turn 14.

The v1 token-suppression sentence is removed. Turn 14 asks only for the immediate verification plan in ordinary prose and does not discuss benchmark tokens.

## 6. Long-distance validity gate

A run is eligible for H1 only when all of the following hold:

1. at least 12 substantive scripted turns occur after state establishment;
2. the final eight scripted turns do not reread marker-bearing docs or WORKING_STATE;
3. the assistant does not echo any primary marker token in its final-eight responses;
4. no marker token is injected by a scripted prompt;
5. no compaction occurs before the fixed boundary;
6. exactly one `system/compact_boundary` event is observed around the scripted `/compact`;
7. the orientation message performs zero tool calls;
8. the Claude Code version/model match their pins;
9. the fixture source checkout has no tracked modifications.

A marker echo is treated like a reread: the run can still be retained for task diagnostics but is excluded from the pre-registered long-distance survival comparison.

## 7. Compaction control and observation

v1 used the locally discovered but previously undocumented `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000`. v2 does not rely on that control.

Current Claude Code documentation exposes `DISABLE_AUTO_COMPACT=1`, which disables automatic compaction while leaving manual `/compact` available. The runner sets it for every arm. It also parses stream output for `type=system, subtype=compact_boundary`, so compaction is observable in A/B without adding observation hooks that would contaminate the native baseline.

`DISABLE_AUTOUPDATER=1` is also set because the harness launches a fresh print-mode Claude process for each resumed turn; a binary update between invocations would invalidate the version pin.

## 8. Primary probe

Immediately after `/compact`, repository/file/network tools are disabled and the model is asked for the six exact durable-state tokens. Unknown values must be returned as `UNKNOWN`; guessing is prohibited.

Primary end-to-end score:

```text
survival_score = exact markers present / 6
```

For B/C the harness also snapshots `state_markers_before_compact`. This supports a second descriptive measure: survival conditional on the marker actually being present in external state. The conditional measure does not replace the end-to-end score and is not used to hide state-maintenance failures.

## 9. Pilot gate

Before any scored sample:

- run A/B/C/D once each with `--dry-run`;
- require `aborted_reason = null` for every arm;
- require `long_distance_valid = true` for every arm intended for H1 comparison;
- inspect only instrumentation/validity, not treatment ranking, when deciding whether the fixture is usable;
- if the protocol changes after this dry run, version it again before scoring.

No efficacy claim, sample-size decision, or withdrawal decision is made from the unscored dry run.
