---
title: Roadmap
date: 2026-09-13
tags: [roadmap, planning]
status: closed
type: reference
---

# Roadmap

> [!important]
> **This roadmap is closed.** The v0.2 mechanism pilot returned `STOP_NO_USEFUL_INCREMENT`
> ([[h1-pilot-results]]), and the assumed progression below — lexical, then semantic, then
> causal/graph memory — is **abandoned**, not paused. It was written before there was any evidence
> that the mechanism it was scaling had value to scale.
>
> Nothing here is a commitment. The sections are kept for the record of what was planned and why it
> stopped, not as work waiting to be picked up.

## v0.1 — deterministic checkpoint (shipped)

- PreCompact writes a deterministic checkpoint
- SessionStart(compact) reinjects at most 9,000 characters
- PostCompact persists the native summary
- `doctor` validates an installation
- `events.jsonl` provides the observability base

Live-validated against Claude Code 2.1.245 (#7). **This stage never claimed efficacy**, and the
pilot that followed did not establish any.

## v0.2 — benchmark (completed, negative)

Completed. The harness was built, three fixture versions were needed to reach a valid measurement,
and the scored pilot returned `STOP_NO_USEFUL_INCREMENT` under its pre-registered rules.

- what was measured and decided: [[h1-pilot-results]]
- what the protocol was: [[h1-pilot-preregistration]]
- where execution departed from it: [[h1-pilot-deviations]]
- what the independent gate found: [[h1-pilot-gate-verdicts]]

Carried items that are now moot because no further stage follows: threshold sweeps, phase-boundary
experiments, session-directory retention.

## v0.3–v0.5 — abandoned

The original plan progressed to lexical retrieval (SQLite FTS/BM25), then embeddings and hybrid
retrieval, then causal/graph memory. **All abandoned.**

Each stage was premised on the previous one showing measurable value. The first one did not. Adding
retrieval machinery now would be rescuing a hypothesis the evidence did not support, which the
registered stopping rule forbids and which [[research-positioning]] argues against on its own
terms.

Abandoned outright, per the pilot's stopping rule:

- rescuing H1 with FTS, embeddings, a vector database, a knowledge graph, or another LLM memory layer
- a harder RouteForge successor selected after seeing these outcomes
- additional sampling until a gap appears
- rescuing the result through the secondary metric
- threshold sweeps
- any claim that operational correctness establishes efficacy

## What could reopen this

Not a plan — conditions. External validation ([[benchmark-plan]], #18) would need **all** of:

1. independent ordinary-use evidence of recurring, costly post-compaction failures **despite**
   accurate maintained state, with a denominator showing how often they occur;
2. traces identifying missing context delivery as the cause, with a concrete reason this mechanism
   would address it;
3. a separately pre-registered study fixing population, task selection, strong native and
   state-only baselines, outcome measures, minimum worthwhile benefit, cost ceiling, sample budget,
   exclusions, and stopping rule — **before** any treatment run.

Pre-registration alone is not sufficient. Choosing a setting because the treatment looks likely to
win there is hypothesis rescue wearing a protocol.
