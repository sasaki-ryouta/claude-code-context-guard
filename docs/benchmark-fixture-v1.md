---
title: Benchmark fixture v1
date: 2026-09-12
tags: [benchmark, fixture, compaction, v0.2]
status: proposed
type: experiment-spec
---

# Benchmark fixture v1 — long-distance state survival

Issue: #13

This is the first deterministic fixture for the v0.2 benchmark. Its purpose is to validate the benchmark harness and measure whether explicit rehydration adds value when important state was established well before a controlled compaction boundary.

It is a **mechanism-isolation fixture**, not sufficient by itself for a broad efficacy claim.

## 1. Experiment question

Primary comparison:

> When high-value state was established early and has not been repeated recently, does Context Guard rehydration increase exact state survival across `/compact` relative to state-only/native compaction?

Secondary comparison:

> Does any survival difference translate into fewer task errors or less rework on a multi-file software task?

## 2. Pinned environment

Before the first pilot, all `TBD` values below MUST be replaced and committed. Do not run a scored pilot with placeholders.

```text
CLAUDE_CODE_VERSION = 2.1.245
MODEL_ID = TBD_EXACT_RESOLVED_MODEL_ID
FIXTURE_SOURCE_COMMIT = TBD_AFTER_FIXTURE_FILES_LAND
FIXED_COMPACT_BOUNDARY = after scripted turn 14, before survival probe
PYTHON = 3.11+
NETWORK = disabled / unnecessary for task
```

The first pilot uses Claude Code 2.1.245 because that is the live-validated lifecycle baseline from #7. A later Claude Code version is a different environment and must be recorded as such.

## 3. Target repository shape

The materialized target is a small stdlib-only Python package named `routeforge`.

```text
routeforge/
├── README.md
├── pyproject.toml
├── src/routeforge/
│   ├── __init__.py
│   ├── model.py
│   ├── parse.py
│   ├── normalize.py
│   ├── route.py
│   ├── cache.py
│   └── export.py
├── tests/
│   ├── test_parse.py
│   ├── test_normalize.py
│   ├── test_route.py
│   └── test_export.py
├── docs/
│   ├── contract.md
│   ├── migration-notes.md
│   └── incident.md
└── .claude/
    └── context-guard/
        └── WORKING_STATE.md   # only in arms B/C
```

The benchmark repository must contain no secrets, external services, package downloads, or network dependency.

## 4. Task story

The package receives event records from two legacy formats and routes normalized records to downstream exporters. The fixture contains a deliberately incomplete migration: normalization logic is duplicated across modules and one path violates a contract discovered during investigation.

The agent must:

1. identify the canonical normalization contract;
2. trace all call sites that bypass it;
3. consolidate behavior without changing public output ordering;
4. fix the defect exposed by the visible tests;
5. preserve less-obvious invariants checked by the hidden evaluator;
6. complete the migration without reintroducing an explicitly rejected approach.

The task is designed so that correct completion requires decisions made in the early investigation phase to remain relevant after compaction.

## 5. Survival markers

These exact tokens are fixture data and may appear in docs / WORKING_STATE, but they must not be repeated by the scripted prompts during the final eight pre-compact turns.

```text
CGV1-GOAL-7F3A
CGV1-CRITERION-B8D2
CGV1-DECISION-2C91
CGV1-FAILURE-6E44
CGV1-NEXT-4D88
CGV1-REJECTED-91AF
```

Semantic mapping:

- `CGV1-GOAL-7F3A`: finish the normalization migration without changing externally observable routing semantics.
- `CGV1-CRITERION-B8D2`: equal routing keys must preserve original input order.
- `CGV1-DECISION-2C91`: canonicalization belongs in one normalization boundary, not duplicated in parser/exporter paths.
- `CGV1-FAILURE-6E44`: one legacy path bypasses canonical normalization and causes the visible failing case.
- `CGV1-NEXT-4D88`: after compaction, verify all bypass call sites before finalizing the refactor.
- `CGV1-REJECTED-91AF`: do not lowercase opaque external identifiers globally; they are case-sensitive.

Markers are deliberately arbitrary. Their exact presence/absence is the machine-scored survival signal; their prose meanings support secondary semantic analysis.

## 6. Arm setup

| arm | state | hooks | note |
|---|---|---|---|
| A | none | none | native baseline |
| B | WORKING_STATE enabled | none | state-only |
| C | WORKING_STATE enabled | Context Guard | rehydration treatment |
| D | none | Context Guard | no-state/no-benefit control |

For B/C, the same CLAUDE.md state-maintenance instructions are used. The harness must not hand-edit state during a run.

## 7. Scripted conversation protocol

The harness drives the same turn sequence for every arm. The model may use tools normally except during the survival probe.

### Early-state phase

**Turn 1 — orient**

Ask the agent to inspect the repository, run visible tests, and identify the migration goal. Do not mention marker tokens in the prompt.

**Turn 2 — establish contract**

Ask it to inspect `docs/contract.md` and `docs/incident.md`, explain the critical invariants, and record high-value working state if that arm uses WORKING_STATE.

This is the last planned full read of marker-bearing state before the fixed compaction boundary.

### Intervening substantive work

Turns 3–14 are task-relevant and fixed in category. Prompt wording is committed with the harness and does not contain marker tokens.

3. trace parser entry points and enumerate normalization call sites
4. trace exporter entry points and identify duplicate normalization
5. inspect routing/order tests and explain the ordering invariant
6. implement the smallest normalization helper change needed for the visible failure
7. migrate one parser path to the canonical helper
8. migrate the second parser path
9. migrate exporter-side duplicate logic
10. run visible tests and classify remaining failures
11. inspect cache-key behavior for compatibility with the migration
12. inspect edge cases around missing/empty fields and update implementation as needed
13. run the full visible suite and review the diff for accidental public-behavior changes
14. state the immediate post-compaction verification plan without rereading marker-bearing docs/state

A turn is substantive only if it results in meaningful inspection, edit, test, or reasoning tied to the task. A harness pilot is invalid if the sequence collapses into fewer than 12 substantive post-state turns because the model combines or skips scripted phases.

## 8. State-distance validity rules

A run is valid for B-vs-C long-distance survival only if all are true:

1. marker-bearing contract/state was established by turn 2;
2. at least 12 substantive turns occur after that point and before `/compact`;
3. none of the final 8 pre-compact scripted prompts contains a marker token;
4. the model does not reread `docs/contract.md`, `docs/incident.md`, or the marker-bearing WORKING_STATE sections during those final 8 turns;
5. the harness does not inject marker text through side channels;
6. `/compact` occurs at the fixed boundary after turn 14 for every arm.

If a model independently rereads marker-bearing material in the final 8 turns, keep the run for task-outcome analysis but exclude it from the pre-registered long-distance survival comparison.

This avoids treating an immediately refreshed state as evidence about rehydration while also avoiding outcome-dependent boundary tuning.

## 9. Compaction and primary probe

After turn 14, the harness invokes `/compact`.

Immediately after compaction, before any repository read, run a dedicated probe with repository/file/network tools disabled.

Probe text:

```text
Without using tools or reopening files, report the exact benchmark tokens you currently remember for:
1. goal
2. acceptance criterion
3. decision
4. unresolved failure
5. next action
6. rejected approach
If you do not remember an item, write UNKNOWN for that item. Do not guess token strings.
```

Primary score is exact string presence in the probe response.

```text
survival_score = number of expected markers present / 6
```

Also record each field as an independent binary variable. Do not use semantic matching for the primary score.

## 10. Task completion after probe

Re-enable normal tools after the probe. Ask the agent to continue from its stated next action and finish the migration.

The final agent output is not the pass criterion. The evaluator is authoritative.

## 11. Evaluator

Two layers:

### Visible evaluator

Executed by the agent during normal work:

```bash
python -m unittest discover -s tests -v
```

### Hidden evaluator

Executed by the benchmark harness outside the target repository after the run. Hidden tests are stored in the benchmark harness, not copied into the materialized target repo.

Hidden checks must cover at minimum:

- stable input ordering for equal routing keys;
- case sensitivity of opaque external identifiers;
- all legacy paths pass through canonical normalization;
- no duplicate fallback normalization remains in parser/exporter paths;
- public output shape remains unchanged;
- visible tests still pass.

Task outcome is machine-verifiable pass/fail plus individual hidden-test results.

## 12. Prompt pinning

The exact text of the initial prompt and each scripted turn MUST live in version-controlled fixture files, not only in this document. The harness records their SHA-256 hashes per run.

No prompt may be edited after pilot outcomes are inspected without incrementing the fixture version.

## 13. Provenance per run

Minimum run record:

```json
{
  "fixture": "v1",
  "arm": "A|B|C|D",
  "fixture_source_commit": "...",
  "target_initial_commit": "...",
  "claude_code_version": "...",
  "model_id": "...",
  "prompt_hashes": ["..."],
  "compact_boundary": "after_turn_14",
  "survival_markers": {"...": true},
  "survival_score": 0.0,
  "visible_tests_pass": false,
  "hidden_tests_pass": false,
  "rehydrate_context_chars": null,
  "hook_errors": 0,
  "wall_time_seconds": 0
}
```

Unknown/unavailable metrics are `null`, never guessed.

## 14. Pilot rules

The pilot is for instrumentation/fixture validation, not efficacy claims.

- run all four arms at least once;
- confirm exact marker scorer works without manual judgment;
- confirm the fixed compact boundary is reached;
- confirm B/C state handling is identical except hooks;
- confirm hidden evaluator cannot be read by the target agent;
- confirm no arm-specific prompt accidentally reveals the condition;
- inspect whether substantive-turn and marker-distance validity rules are satisfied.

Do not choose the final sample size or make a withdrawal decision from the one-run-per-arm pilot.

## 15. Milestone-1 completion gate

Milestone 1–2 is complete only when:

- target fixture files are committed;
- materialization produces a deterministic target repository;
- the target initial commit SHA is pinned here;
- exact initial + scripted prompts are committed;
- exact model identifier is pinned;
- Claude Code version is pinned;
- visible and hidden evaluator commands are committed;
- fixed compact boundary is committed;
- marker scorer is committed and unit-tested;
- one unscored dry run proves the harness can execute the protocol end-to-end.
