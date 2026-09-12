---
title: Research positioning and prior art
date: 2026-09-12
tags: [research, benchmark, prior-art, memory, compaction]
status: active
type: reference
---

# Research positioning and prior art

This document records what Context Guard should treat as **already established**, what remains **project-specific and unresolved**, and how that changes the benchmark plan.

The purpose is to avoid spending benchmark budget re-proving generic facts about long context or agent memory. Context Guard should only run experiments that can change a product or research decision.

> [!important]
> The narrow research question is:
>
> **Does a small, project-local, training-free working state that is explicitly re-injected after Claude Code compaction provide incremental value over Claude Code's native compaction and documented best practices, without requiring another model or an external retrieval database?**

## 1. What we should not re-prove

### 1.1 Long context is not equivalent to perfect recall

This is established enough to use as background rather than a project hypothesis.

- *Lost in the Middle* shows that long-context models can use relevant information unevenly depending on where it appears in context.
- *LongMemEval* reports substantial degradation in sustained-history memory and provides a dedicated benchmark for extraction, temporal reasoning, updates, and abstention.
- Claude Code's own best-practices documentation states that performance degrades as the context window fills and recommends aggressive context management.

Context Guard therefore does **not** need an experiment whose conclusion is merely "long contexts forget things."

### 1.2 Compaction is a lossy compression boundary

Claude Code documents that automatic compaction summarizes conversation history, that early conversation-only instructions may be lost, and that a `Compact Instructions` section in `CLAUDE.md` can influence what is preserved.

Project-root `CLAUDE.md` is re-read after `/compact`, so a weak baseline that omits documented native persistence mechanisms is not an adequate external efficacy baseline.

Context Guard therefore does **not** need to prove that native compaction can lose detail. The relevant question is whether explicit state + rehydration adds value **beyond a strong native configuration**.

### 1.3 Agent memory can help in some settings

This is also no longer a useful generic research question.

- *EvoMemBench* compares representative agent-memory methods and strong long-context baselines. Its result is not "memory always wins": long-context baselines remain competitive, memory helps more when context is insufficient or tasks are difficult, and no single memory form dominates every setting.
- *SWE-MeM* directly studies adaptive memory management for long-horizon software-engineering agents and reports gains on SWE-bench-style coding tasks. It is materially more complex than Context Guard because it trains a memory-management policy.
- *AgenticSTS* demonstrates a bounded, typed, ablatable memory contract and is useful methodological prior art for isolating memory components.

Context Guard therefore should not claim novelty from the statement "coding agents benefit from memory." Its possible contribution is the **minimality of the mechanism** and the causal value of post-compaction rehydration.

### 1.4 Long-horizon software engineering already has external benchmarks

We do not need to invent a large proprietary task suite to establish external validity.

Candidate external validation sets include:

- SWE-bench / SWE-bench Verified for established repository-level issue resolution;
- SWE-Bench Pro / SWE-Bench Pro Verified for harder, longer-horizon repository tasks;
- RoadmapBench for multi-target real version-upgrade work.

RouteForge should therefore remain a controlled mechanism fixture, not the sole basis for a real-world efficacy claim.

## 2. What remains unresolved and worth measuring

### RQ1 — Incremental value of rehydration

The most important causal comparison is:

- **B: explicit WORKING_STATE, no rehydration hooks**
- **C: the same WORKING_STATE behavior, plus post-compaction rehydration**

If B and C are otherwise identical, B vs C isolates the incremental contribution of re-injection after compaction.

This is the central Context Guard question. Existing memory literature does not answer it for Claude Code's native compaction lifecycle and this deliberately minimal mechanism.

### RQ2 — Value over a strong native baseline

For external efficacy work, the baseline must use Claude Code's documented native best practices rather than an intentionally weak configuration.

A strong native baseline should be allowed to use common, arm-independent compact-preservation instructions in `CLAUDE.md`. State-specific instructions belong only to state arms, but generic native compaction guidance must not be withheld just to make Context Guard look better.

The external comparison is therefore not "nothing vs Context Guard". It is closer to:

1. native Claude Code + documented compaction best practices;
2. native + explicit working state;
3. native + explicit working state + Context Guard rehydration.

### RQ3 — Operational cost

The 9,000-character injection cap, hook duration, total wall time, compaction metadata, and token observations are important, but they do not require a separate hypothesis test before efficacy exists.

Treat these as **cost accounting** attached to every run.

### RQ4 — Real task outcome

After mechanism validity is established, the relevant external question is whether Context Guard improves real coding outcomes: task completion, regressions, repeated investigation, and total cost.

This should move to an existing public software-engineering benchmark rather than continually increasing RouteForge difficulty after observing results.

## 3. Consequences for the current experiment plan

### 3.1 RouteForge v3 is a mechanism/isolation fixture

Its job is to establish that the harness can cleanly separate arms and measure long-distance survival without marker leakage, state-control contamination, or uncontrolled compaction.

Once one real A/B/C/D unscored dry run passes the pre-registered validity/manipulation checks:

- freeze v3;
- do not tune task difficulty based on arm outcomes;
- do not build v4 merely to obtain a larger performance gap;
- use only the minimum controlled samples needed to answer the mechanism question;
- move real-world efficacy to an external benchmark protocol.

### 3.2 D is primarily a negative control

D (hooks without curated state) is useful for proving that hook presence alone does not create the effect and for detecting unintended state creation. It need not dominate the sample budget after the mechanism is validated unless evidence suggests hook-only behavior is itself unstable.

### 3.3 H2 becomes accounting, not a standalone benchmark program

Record context injection size, hook latency, wall time, and available token observations, but do not spend a separate large experiment proving that a hard-coded 9,000-character cap is bounded.

### 3.4 Threshold optimization is deferred

Do not sweep compaction thresholds before showing that rehydration has useful incremental value. Threshold tuning is an optimization problem downstream of a positive mechanism result, not a prerequisite for v0.2.

### 3.5 External validation follows mechanism validation

After RouteForge validity and a small causal pilot, define a separate, pre-registered protocol over an existing public SWE benchmark. Preserve the same model/version pinning and controlled compaction intervention where technically possible.

## 4. Claude Code-specific contamination controls

This review identified one concrete blocker before the next v3 dry run.

### 4.1 Disable native Auto Memory in every arm

Claude Code Auto Memory is enabled by default and loads per-repository memory at session start. That is a second persistent-memory channel and can confound a Context Guard memory experiment.

Every controlled benchmark run should set:

```text
CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
```

The run record should state that this control was active.

### 4.2 Prefer `--bare` for scripted evaluation when authentication permits

Claude Code documents `--bare` as the recommended mode for scripted/CI calls because it skips automatic discovery of hooks, skills, plugins, MCP servers, Auto Memory, and `CLAUDE.md`; only explicitly supplied flags take effect.

However, bare mode also skips OAuth/keychain reads. The current local benchmark workflow uses authenticated Claude Code, so moving to `--bare` must not silently change the authentication path or model-access environment.

Decision:

- **now:** explicitly disable Auto Memory and continue recording model/version/config provenance;
- **later:** prefer `--bare` once the benchmark has a reproducible authentication path compatible with bare mode;
- never mix bare and non-bare runs inside one scored comparison.

### 4.3 Host-level configuration is part of provenance until bare mode is used

Without `--bare`, `claude -p` can discover configuration from the working directory and `~/.claude`. Controlled runs must therefore avoid relying on undocumented host state and should record enough provenance to identify accidental configuration drift.

## 5. Interpretation rules

A positive RouteForge canary result is evidence for a **memory transmission mechanism**, not by itself evidence of better software engineering.

A positive semantic probe is stronger than exact canary survival, but still remains an internal fixture result.

A convincing Context Guard efficacy claim requires both:

1. controlled evidence that rehydration contributes incrementally beyond state-only/native mechanisms; and
2. external task evidence that the gain matters for actual software-engineering outcomes at acceptable cost.

Negative results are also useful:

- B ≈ C under a valid fixture means explicit rehydration may add little beyond maintained state/native compaction;
- C improves survival but not external task outcome means Context Guard is a memory aid without demonstrated SWE benefit;
- C improves task outcome but at excessive cost means budget/trigger design needs revision before richer retrieval is justified.

## 6. References reviewed 2026-09-12

Claude Code documentation:

- Best practices: https://code.claude.com/docs/en/best-practices
- How Claude Code works: https://code.claude.com/docs/en/how-claude-code-works
- Project memory / Auto Memory: https://code.claude.com/docs/en/memory
- Environment variables: https://code.claude.com/docs/en/env-vars
- Programmatic / bare mode: https://code.claude.com/docs/en/headless
- CLI reference: https://code.claude.com/docs/en/cli-usage

Research and benchmarks:

- Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*: https://arxiv.org/abs/2307.03172
- Wu et al., *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory*: https://arxiv.org/abs/2410.10813
- Wang et al., *EvoMemBench: Benchmarking Agent Memory from a Self-Evolving Perspective*: https://arxiv.org/abs/2605.18421
- Gao et al., *SWE-MeM: Learning Adaptive Memory Management for Long-Horizon Coding Agents*: https://arxiv.org/abs/2606.28434
- Cheng et al., *AgenticSTS: A Bounded-Memory Testbed for Long-Horizon LLM Agents*: https://arxiv.org/abs/2607.02255
- Deng et al., *SWE-Bench Pro: Can AI Agents Solve Long-Horizon Software Engineering Tasks?*: https://arxiv.org/abs/2509.16941
- Zheng et al., *SWE-Bench Pro Verified: A Reliable Benchmark for Software Engineering Agents*: https://arxiv.org/abs/2609.08149
- Xu et al., *RoadmapBench: Evaluating Long-Horizon Agentic Software Development Across Version Upgrades*: https://arxiv.org/abs/2605.15846

Most 2026 research items above are recent preprints. Treat their conclusions as prior evidence and methodological input, not unquestioned ground truth.