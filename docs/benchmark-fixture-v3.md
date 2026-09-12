---
title: Benchmark fixture v3
date: 2026-09-12
tags: [benchmark, fixture, compaction, v0.2]
status: proposed
type: experiment-spec
---

# Benchmark fixture v3 — decoupled long-distance recall

Issues: #13, #21

Fixture v3 replaces invalid v2 for the H1 mechanism-isolation question. v2 is retained unchanged as a failed validity pilot.

## 1. Primary question

When opaque recall payload was established early, was not reread or echoed during the final eight pre-compact turns, and is optionally preserved in explicit working state, does Context Guard rehydration increase exact recall survival across a fixed `/compact` boundary?

This fixture measures the state-transfer mechanism. Task-outcome sensitivity is a separate H3 fixture tracked in #18.

## 2. Environment pins

- Claude Code: `2.1.245`
- model: `claude-sonnet-5`
- compact boundary: immediately after scripted turn 14
- auto compaction: disabled with `DISABLE_AUTO_COMPACT=1`
- native Auto Memory: disabled with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` in every arm, so the
  per-repository memory channel cannot confound the state/rehydration comparison
  (see [[research-positioning]] 4.1); the control is recorded per run as `auto_memory_control`
- auto updater: disabled with `DISABLE_AUTOUPDATER=1`
- network: unnecessary / not allowed by work-tool policy

Any version or model drift aborts the run.

## 3. Arms

| arm | WORKING_STATE | hooks | hook delivery |
|---|---|---|---|
| A | no | no | none |
| B | yes | no | none |
| C | yes | yes | inline `--settings` |
| D | no | yes | inline `--settings` |

Hook configuration is never written to the target repository. This prevents hook metadata from becoming task-visible repository content.

Manipulation check before compact:

- A/D: `WORKING_STATE.md` must be absent.
- B/C: `WORKING_STATE.md` must exist and contain all six recall canaries.

A run failing this check is invalid rather than reclassified.

## 4. Semantic task state versus recall canaries

Task semantics live in normal prose in `docs/contract.md` and `docs/incident.md`.

Exact canaries live separately in `docs/recall-tags.md`. They are intentionally inert and must not be used as names for invariants, decisions, or implementation concepts.

The six fields are:

- goal
- order
- boundary
- id_case
- shape
- rejected

The exact token values are committed in `benchmarks/fixture_v3/markers.json` and the one-time target recall document. Scripted prompts never contain the token strings.

Turn 2 instructs the model that exact canary output is forbidden in ordinary progress responses but explicitly permitted when a later prompt specifically asks for recall tags. This is not a contradiction: the exception is part of the original instruction.

## 5. Distance protocol

- Orientation is tool-disabled and non-substantive.
- Turn 1 performs repository orientation and visible tests.
- Turn 2 reads contract, incident, and recall-tag material and establishes state.
- Turns 3–14 are task-relevant investigation / implementation / verification.
- No scripted turn after turn 2 asks to reopen contract, incident, recall-tags, or WORKING_STATE.
- Final-eight turns are turns 7–14.
- `/compact` occurs only after turn 14.

Long-distance validity requires:

1. at least 12 substantive turns after turn 2;
2. no final-eight read of contract, incident, recall-tags, or WORKING_STATE;
3. no exact recall-canary echo in assistant output during the final eight turns;
4. no pre-boundary `system/compact_boundary` event;
5. exactly one compact boundary around scripted `/compact`;
6. orientation tool use count is zero;
7. arm manipulation check passes;
8. target `.claude/settings.json` is absent;
9. C/D have zero hook errors and `rehydrate_context_chars <= 9000`.

## 6. Primary exact probe

Immediately after compact, with repository/file/network tools disabled, ask for the six exact recall tags. The prompt contains no token strings.

Primary outcome:

```text
survival_score = exact canaries present / 6
```

Each canary is also retained as an independent binary outcome.

No H1 comparison uses a run where `long_distance_valid != true`.

## 7. Secondary semantic probe

After the exact recall probe and before tools are re-enabled, ask six fixed multiple-choice questions about durable fixture facts. The answer key is committed outside the target in `semantic_answers.json`.

The semantic probe is machine-scored by exact `Qn=<A|B|C>` output. It is secondary and is not substituted for the primary canary mechanism measure.

## 8. Evaluators and task completion

Visible and hidden RouteForge evaluators remain machine-verifiable. They are retained for regression / task-outcome context, but v3 is not tuned to make pass/fail discriminate after the v1/v2 observations. H3 is #18.

## 9. Pilot rule

Run one A/B/C/D unscored validity pass first. Do not interpret arm ordering, survival scores, or semantic scores from that run as efficacy evidence.

If protocol validity fails, version again before changing prompt wording or marker design. If all validity checks pass, freeze the fixture and pre-register the scored-pilot sample and analysis plan before collecting scored samples.
