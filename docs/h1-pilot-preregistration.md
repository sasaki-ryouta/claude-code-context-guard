---
title: H1 pilot pre-registration
date: 2026-09-13
tags: [benchmark, preregistration, h1, v0.2]
status: registered
type: experiment-protocol
---

# H1 pilot pre-registration — RouteForge fixture v3

Issues: #13, #21. Registered **before** any scored run and before any scored outcome was observed.

This protocol is fixed at the commit that introduces it. Nothing below may be changed after the first scored run starts. If something must change, the pilot is abandoned and re-registered under a new fixture version.

## 1. Question

> In a valid, frozen RouteForge v3, does Context Guard rehydration (arm C) add incremental value over maintained working state alone (arm B)?

This is a **mechanism** question (H1). It is not a software-engineering outcome claim; that is H3 and lives in #18.

## 1b. What was known at registration

Stated plainly, because this is prospective scored sampling rather than a fully outcome-blind design:

- **no scored run has been executed**; every stored run record has `scored: false`;
- one **unscored** validity run was observed before this document was written, in which the primary
  score was A=0.0, B=0.0, C=1.0, D=0.0 and the secondary score was 1.0 in all four arms;
- those observations are **excluded from the scored aggregate** and are not pooled with pilot data;
- the contaminated pre-control runs, in which every arm scored 6/6, are quarantined and excluded.

The thresholds, ordering, sample size, and decision rules below were chosen to be defensible under
either direction of result, and the ceiling rule was written because saturation was observed in the
contaminated runs — not because a favourable scored outcome was known.

## 2. Primary comparison

**B vs C.** Both arms receive byte-identical state assets and the same state-maintenance instructions; they differ only in whether Context Guard hooks are installed via inline `--settings`. All other arms are controls.

## 3. Primary outcome

`survival_score` from the post-compact exact-canary probe: the proportion of the six durable recall tags reproduced verbatim, scored by the existing deterministic machine scorer (`benchmarks/fixture_v3/score_markers.py`). Range 0.0–1.0 in steps of 1/6.

Aggregate per arm as the **arithmetic mean over valid scored runs**.

Effect measure: `mean(C) - mean(B)`, reported with per-run values and the count of valid runs.

## 4. Secondary outcome

`semantic_probe.score`: six fixed multiple-choice questions about durable fixture facts, machine-scored against a committed answer key. Reported the same way. Secondary only. It is reported descriptively and **never changes the decision**: it cannot
trigger GO, and it cannot rescue or override a primary result, including a saturated or
adverse one. Section 5 states the same rule from the other direction.

## 5. Ceiling and floor rules (fixed in advance)

The contaminated pre-control run had every arm at 6/6, so a saturating instrument is a real
possibility and must be handled before results exist.

**The primary endpoint always decides.** The secondary endpoint is reported descriptively and
never changes the decision. This is deliberate: allowing a fallback to the secondary endpoint would
let a saturated or adverse primary contrast be overridden by a different measure chosen after the
fact, and section 4 already forbids a secondary-only GO.

Saturation is declared only when the primary comparison cannot discriminate — that is, when the
arms are pinned together at an extreme:

- **INCONCLUSIVE_CEILING** when `mean(B) >= 0.95` **and** `mean(C) >= 0.95`;
- **INCONCLUSIVE_FLOOR** when `mean(B) <= 0.05` **and** `mean(C) <= 0.05`.

Both require *both* arms at the extreme. A high or low `mean(B)` alone is not saturation if `C`
differs from it: that is a measurable contrast and section 6 decides it normally.

Either inconclusive state resolves to **STOP_NO_USEFUL_INCREMENT**, recorded explicitly as *"no
measurable increment because the instrument saturates"* rather than as evidence that rehydration is
useless. A saturating instrument is not repaired by adding retrieval machinery: under any
inconclusive outcome, richer retrieval (FTS, embeddings, vector DB, graph, extra LLM memory) is
**not** added to rescue the hypothesis.

An adverse primary contrast can never be reported as inconclusive. If `d < 0`, the decision is
STOP under section 6 regardless of where the means sit.

## 6. Interpretation thresholds

Let `d = mean(C) - mean(B)` on the primary outcome over valid runs. Thresholds are exact fractions
of the six-canary scale, not decimal approximations: one canary is `1/6`, evaluated as
`Fraction(1, 6)` so the decision boundary is unambiguous.

Decisions are evaluated in this order, and the first matching rule applies:

| # | condition | decision |
|---|---|---|
| 1 | `d < 0` | STOP_NO_USEFUL_INCREMENT (adverse contrast) |
| 2 | both arms saturated per section 5 | STOP_NO_USEFUL_INCREMENT (inconclusive: instrument saturates) |
| 2b | `d == 0` | STOP_NO_USEFUL_INCREMENT (no increment) |
| 3 | `d >= 1/6` **and** `C > B` in at least 4 of the 5 matched blocks | GO_EXTERNAL_VALIDATION |
| 4 | `d >= 1/6` but not directionally consistent | STOP_NO_USEFUL_INCREMENT (unstable signal) |
| 5 | `0 < d < 1/6` | STOP_NO_USEFUL_INCREMENT (increment too small to justify external validation cost) |

An adverse contrast is decided **before** saturation, so a negative result can never be hidden
behind a ceiling. A zero contrast is decided **after** saturation, so two arms pinned at an extreme
are recorded as a saturating instrument rather than as a measured absence of effect — those are
different claims and the distinction is fixed here rather than chosen later.

These are **decision** thresholds for whether to spend external-benchmark budget, not significance
claims. With this sample size no p-value or confidence interval will be reported as if it were
confirmatory; any dispersion statistic is descriptive only.

## 7. Sample plan

Total scored runs: **12** (hard cap).

| arm | scored runs | role |
|---|---|---|
| B | 5 | primary |
| C | 5 | primary |
| A | 1 | native baseline / negative control |
| D | 1 | hooks-without-state control |

The budget is concentrated on B/C because they are the causal contrast. A and D exist to detect manipulation failure, not to be compared for efficacy.

## 8. Ordering, interleaving, randomization

Runs execute in **matched B/C pairs** to balance drift in service conditions across the comparison.

- five blocks; each block contains one B run and one C run;
- within each block the order of B and C is randomized;
- the randomization uses Python `random.Random(20260913)` — seed fixed here, before any scored run;
- A and D run once each, after block 3, to sit in the middle of the series rather than at either end;
- the realized order, computed from that seed before any scored run, is:

```text
 1  C     5  C      9  B
 2  B     6  B     10  C
 3  C     7  A     11  B
 4  B     8  D     12  C
```

Reproduce with `random.Random(20260913)`, shuffling `["B", "C"]` once per block and inserting A and D after block 3. This order is fixed here; it is not recomputed at run time and not adjusted afterwards.

## 9. Validity and exclusion

A scored run is **excluded** from aggregation if `long_distance_valid` is false or
`aborted_reason` is non-null, as judged solely by the pre-registered machine checks already
implemented in `_validity()`. Validity is never judged by looking at `survival_score` or the
secondary score.

Replacement is **mandatory and immediate**, not a choice:

- when a run is excluded, its replacement is executed **before the next scheduled run**, using the
  same arm and protocol, and before any aggregate is computed;
- the operator never decides *whether* to retry — only the schedule below applies;
- at most **two** replacements across the whole pilot;
- a third exclusion ends the pilot immediately as **HARD_BLOCKER: too many invalid runs**, with no
  decision issued.

Replacements are additional to the 12 scheduled runs: the cap in section 7 counts scheduled runs,
and the pilot executes at most 14 Claude Code run invocations in total.

If exclusions still leave fewer than **5** valid runs in either B or C — that is, if a matched
block cannot be completed within the replacement budget — the pilot reports **HARD_BLOCKER:
insufficient valid samples** and no decision is issued. A block with one valid arm and one
permanently invalid arm is dropped from the directional-consistency count in section 6 rule 3, and
the drop is reported.

Excluded runs are retained in provenance and listed in the result summary with their exclusion
reason.

## 10. No outcome-dependent extension

Explicitly prohibited once the first scored run starts:

- increasing the sample count;
- adding arms;
- changing prompts, canaries, arm definitions, the compact boundary, or task difficulty;
- changing the primary or secondary metric;
- changing thresholds or the aggregation rule;
- continuing to run until a difference appears.

## 11. Cost accounting

Recorded per run, reported as descriptive accounting rather than tested hypotheses:

- wall time;
- `rehydrate_context_chars` (hook arms);
- compaction `pre_tokens` / `post_tokens` / `cumulative_dropped_tokens`;
- hook error count;
- number of scripted turns and tool calls.

## 12. Frozen environment

```text
CLAUDE_CODE_VERSION = 2.1.245
MODEL_ID            = claude-sonnet-5
FIXTURE             = v3 (frozen)
FIXTURE_COMMIT      = ca5e677b1a448c1a91ac0bbd2f02644404d45855 (fixture frozen)
TARGET_INITIAL      = c95860f6314c944eb487748002672adea93b2db8
COMPACT_BOUNDARY    = after scripted turn 14
AUTO_COMPACTION     = DISABLE_AUTO_COMPACT=1
NATIVE_AUTO_MEMORY  = CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
HOST_CONFIG         = --setting-sources project
AUTO_UPDATE         = DISABLE_AUTOUPDATER=1
```

Version or model drift aborts a run; aborted runs are excluded under section 9.

## 13. Execution

Each scored run is a single arm invocation with scoring enabled:

```bash
python -m benchmarks.fixture_v3.run_arm --arm <ARM>
```

run in the order of section 8, from a clean checkout at the frozen fixture commit. `--dry-run` is omitted, so `scored` is true in the run record. Runs are sequential; no two arms execute concurrently.

## 14. Deliverables

- machine-readable aggregate (`benchmarks/runs/h1-pilot/aggregate.json`);
- human-readable summary;
- cost accounting;
- the realized run order;
- the decision, with the rule from section 6 that produced it.
