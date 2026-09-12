---
title: H1 pilot independent gate verdicts
date: 2026-09-13
tags: [benchmark, review, h1, integrity]
status: final
type: experiment-record
---

# Independent gate verdicts

Every phase of the H1 work passed through an independent read-only engineering/research gate
(Codex CLI, GPT-6 Astra) with no authority to change code and no role in scoring. The primary
exact-marker score came from the deterministic machine scorer throughout; the gate was explicitly
forbidden from overriding it.

The gate blocked **nine times**. Each block is listed because the sequence is the evidence that the
result was not simply asserted.

## Gate 1 — contamination controls

| round | verdict | blocker |
|---|---|---|
| 1 | BLOCK | A host plugin `SessionStart` hook injected the **previous arm's session summary** into the next arm (A→B→C→D). Arms were not independent in any run up to that point. |
| 1 | BLOCK | `_validity()` returned true for records that predated the Auto Memory control, and accepted an explicit `=0`. |
| 2 | PASS | Both resolved; 13/13 uncontrolled historical records confirmed rejected. |

## Gate 1b — after the first isolated run failed

| round | verdict | blocker |
|---|---|---|
| 1 | BLOCK | The "tools-disabled" probe still exposed `TaskOutput`; a synthetic probe retrieving the canaries scored 1.0 and stayed valid. |
| 2 | BLOCK | A final-eight `Grep` over marker material produced `reads=[] echoes=[]`. |
| 3 | BLOCK | A bare-filename `WORKING_STATE.md` read evaded the anchored suffix check. |
| 4 | BLOCK | `cd docs && cat contract.md` evaded path-qualified needles. |
| 5 | BLOCK | A repository-wide search returned contract.md content while naming no document and echoing no canary. |
| 6 | PASS | Detection no longer depends on enumerating tool names. |

## Gate 2 — validity of the completed unscored run

PASS. Audited the raw stream logs rather than the harness's own `long_distance_valid` flag,
recomputed all 18 prompt hashes per arm, checked 76/76 init records, and confirmed B and C differ
only by the rehydration package. Explicitly confirmed that validity was judged **without**
reference to `survival_score` or the secondary score.

## Gate 3 — pre-registration

| round | verdict | blocker |
|---|---|---|
| 1 | BLOCK | The ceiling fallback let an **adverse** primary contrast (B=1, C=0) be declared inconclusive and then overridden by a secondary GO. |
| 1 | BLOCK | Replacement of invalid runs was optional, permitting result-dependent sampling — demonstrated with a worked example flipping GO to STOP. |
| 2 | PASS | Verified across 5,766 aggregate/count combinations that every non-positive contrast selects rule 1 and every GO satisfies both registered thresholds. |

## Gate 4 — final research gate

| round | verdict | blocker |
|---|---|---|
| 1 | BLOCK | All runs executed at a different commit from the pinned fixture commit. |
| 1 | BLOCK | No human-readable summary existed, so conclusion scope could not be audited. |
| 2 | BLOCK | The write-up said the excluded run scored 6/6; it scored **0/6**, and the exclusion therefore *raised* the treatment arm's mean. |
| 2 | BLOCK | The deviation record's "execution was impossible" justification was false — `run_arm --arm` existed at the pinned commit. |
| 2 | BLOCK | Tool-call totals counted scripted turns only (590 rather than 663). |
| 3 | BLOCK | The compliance list still repeated the corrected 6/6 claim, leaving the record self-contradictory. |
| 4 | **PASS** | Protocol compliance, validity, arithmetic including the sensitivity analysis, conclusion scope, and rule adherence all confirmed. |

## What the blocks were mostly about

Seven of the nine concerned **measurement integrity** — paths by which a contaminated run could
have been judged valid, or by which retrieved information could have passed as recalled
information. Two concerned **decision integrity** — ways the registered rules could have produced a
biased conclusion. Three of the Gate 4 blocks were errors in how I described the result, and two of
those would have made the finding look stronger than it is.

None of the blocks were about the outcome being unfavourable. The gate was never asked whether the
result was good.
