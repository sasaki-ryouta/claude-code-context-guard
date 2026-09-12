---
title: H1 pilot results
date: 2026-09-13
tags: [benchmark, results, h1, v0.2]
status: final
type: experiment-record
---

# H1 pilot results — RouteForge fixture v3

Protocol: [[h1-pilot-preregistration]]. Departures from it: [[h1-pilot-deviations]].
Fixture: [[benchmark-fixture-v3]] (frozen). Positioning: [[research-positioning]].

## Decision

> **STOP_NO_USEFUL_INCREMENT** — registered rule 4: the increment clears the threshold but is not
> directionally consistent.

Produced by the machine aggregator applying the pre-registered rules in their registered order. No
rule was reinterpreted after results were seen.

## Primary outcome — exact canary survival

| arm | per-run scores | mean |
|---|---|---|
| B (working state only) | 0, 1, 1, 1, 1 | **0.80** |
| C (working state + rehydration) | 1, 1, 1, 1, 1 | **1.00** |

- `d = mean(C) - mean(B) = 1/5`, which clears the registered threshold of `1/6`;
- matched blocks favouring C: **1 of 5**, against a registered requirement of at least 4.

Four of the five blocks are ties at 1.0. C never lost a block; it simply had almost nothing to win.
The registered consistency requirement is what decides the outcome, and it was fixed before any
scored run precisely so that a single-block difference could not be presented as a mechanism result.

## Secondary outcome — semantic probe

1.0 in every valid run of both arms. Fully saturated, and by registration it is descriptive only:
it cannot trigger GO and cannot override the primary result.

## What this does and does not say

**It does not show that rehydration fails.** Every observed difference favoured C, and C never
scored below B in any block. The evidence is a positive but inconsistent increment, which the
registered rule treats as insufficient grounds for spending external-validation budget — not as a
demonstration of no effect.

**It does show that maintained working state alone already carries this fixture.** Arm B recalled
all six canaries in four of five runs without any rehydration hook. In this fixture, on this task,
at this boundary, explicit state plus native compaction is close to sufficient on its own, which
leaves little headroom for rehydration to demonstrate value.

**The baseline is high but not by the registered definition of saturation.** `mean(B) = 0.80` sits
below the 0.95 ceiling threshold, so the ceiling rule did not fire and this is not recorded as an
inconclusive-saturation result. It is a measured, directionally weak increment. That said, the
practical reason the consistency requirement failed is headroom: with B at 1.0 in four blocks, C
could only tie.

**It is a mechanism result, not a software-engineering result.** Canary survival measures whether
state crosses a compaction boundary. It says nothing about whether that improves real coding
outcomes, which is H3 and lives in #18.

**n is small by design.** Five valid runs per primary arm support a directional decision about
budget, not a significance claim. No p-value or confidence interval is reported, and none should be
inferred.

## Execution summary

| | |
|---|---|
| scheduled runs | 12 (B×5, C×5, A×1, D×1) |
| executed runs | 13 (one mandatory replacement) |
| excluded runs | 1 |
| replacements used | 1 of 2 permitted |
| halted | no |
| wall time | 2.31 h |
| tool calls | 590 |

### The excluded run

Position 5, arm C. It reread marker-bearing material twice during the final eight turns, which the
frozen validity check rejects. **The exclusion was driven by protocol, not by score** — that run had
in fact recalled all six canaries. It was replaced immediately with another arm-C run, before the
next scheduled run and before anything was aggregated, exactly as registered.

### Controls

| arm | role | primary |
|---|---|---|
| A | native baseline, no state, no hooks | 0.0 |
| D | hooks without curated state | 0.0 |

Both behaved as controls should: without curated state, the canaries did not survive the boundary,
whether or not hooks were installed. D confirms that installing hooks does not by itself produce
survival.

## Cost accounting

Descriptive; feeds no decision rule.

| arm | mean wall time | mean tool calls | rehydration chars | hook errors |
|---|---|---|---|---|
| A | 561 s | 43.0 | — | — |
| B | 623 s | 43.2 | — | — |
| C | 673 s | 47.8 | 3430–4429 | 0 |
| D | 588 s | 44.0 | 619 | 0 |

Compaction dropped roughly 95k–107k tokens per run across arms. C's rehydration stayed well inside
the 9,000-character cap. C is the slowest arm by about 8% over B, which is the cost side of the
mechanism and is worth carrying forward if it is ever revisited.

## Consequences

Per [[research-positioning]] and the registered stopping rule:

- **do not** add FTS, embeddings, a vector database, a knowledge graph, or another LLM memory layer
  to rescue this result;
- **do not** raise RouteForge difficulty after seeing these outcomes — a harder fixture chosen now
  would be tuned to observed behaviour;
- external validation (#18, SWE-bench-style work) is **not** started on the strength of this pilot.

If the mechanism is revisited later, the honest next question is not "how do we make C win" but
"is there a realistic setting where maintained state alone is *not* already sufficient" — and that
question needs a fixture designed before any arm is run, not this one adjusted afterwards.
