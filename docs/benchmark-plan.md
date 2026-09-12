---
title: Benchmark plan
date: 2026-09-12
tags: [benchmark, evaluation, compaction]
status: active
type: reference
---

# Benchmark plan (v0.2)

v0.1.x established **lifecycle correctness and operational safety**. It did not establish efficacy.

Before extending the benchmark, review [[research-positioning]]. That document records the prior-art review and defines what this project will no longer spend experiment budget re-proving.

> [!important]
> v0.2 is now deliberately narrower:
>
> **Measure the incremental value of explicit post-compaction rehydration over Claude Code native compaction, documented native best practices, and explicit working state alone.**

## 1. Research questions

### H1 — rehydration increment

Does re-injecting curated project-local working state after compaction preserve durable task state better than the same working-state practice without rehydration?

The primary causal comparison is **B vs C**.

### H2 — operational cost

What does that mechanism cost in injected context, hook latency, wall time, and observable token use?

H2 is **cost accounting**, not a separate large benchmark program. The implementation already enforces a 9,000-character recovery-context ceiling.

### H3 — real software-engineering outcome

Does the mechanism improve completion/regression/rework outcomes on realistic repository-level tasks?

H3 should be validated on an existing public SWE benchmark after the controlled mechanism fixture is valid. Do not keep increasing RouteForge difficulty after observing arm outcomes.

### Deferred — threshold optimization

Do not optimize compaction timing/window until H1 or H3 demonstrates useful incremental value. Threshold sweeps are downstream optimization, not a v0.2 prerequisite.

## 2. Experimental conditions

The mechanism fixture keeps four arms for isolation:

| arm | explicit WORKING_STATE | Context Guard hooks | role |
|---|---|---|---|
| **A. native** | no | no | native control |
| **B. state only** | yes | no | isolates the value of explicit state maintenance |
| **C. full** | yes | yes | state + post-compaction rehydration |
| **D. hooks only** | no | yes | negative control for hook-only effects / unintended state creation |

For causal interpretation:

- **B vs C** isolates rehydration if all state behavior is otherwise identical.
- **A vs B** estimates the contribution of explicit state maintenance.
- **D** verifies that hooks without curated state do not create the claimed effect or cause state contamination.

For later external efficacy work, A must be a **strong native baseline** using Claude Code's documented, arm-independent compaction best practices. Do not intentionally withhold generic `Compact Instructions` merely to weaken the native condition.

## 3. RouteForge fixture scope

RouteForge v3 is a **mechanism and measurement-isolation fixture**, not the final external-validity benchmark.

It exists to prove that the harness can enforce:

- fixed manual compaction boundary;
- no pre-boundary compaction;
- early state discovery followed by at least 12 substantive turns;
- no survival-canary reread in the final 8 pre-compact turns;
- no survival-canary echo in the final 8 pre-compact turns;
- tools-disabled post-compaction probes;
- state manipulation by arm: A/D absent, B/C present with all canaries;
- hook health and bounded rehydration for C/D;
- exact model / Claude Code version pinning;
- target and hidden-evaluator isolation.

See [[benchmark-fixture-v3]] for the fixture-specific contract.

### Stop rule for fixture engineering

Once one real A/B/C/D **unscored** v3 run passes all validity and manipulation checks:

1. freeze v3;
2. do not tune prompts/task difficulty to amplify arm differences;
3. do not create v4 solely because a valid pilot produces a small effect;
4. run only the minimum controlled sample needed to establish whether the mechanism is directionally worth external validation;
5. move task-outcome validation to an existing public SWE benchmark.

## 4. Survival measurement

### Primary: exact canary transmission

Use opaque canaries that are not task vocabulary. The canaries are attached to durable state fields and requested only in the post-compaction probe.

The score is machine-verifiable exact-string presence/absence. Do not use LLM-as-judge for the primary binary survival score.

### Secondary: semantic state probe

Use a fixed, tools-disabled, machine-scored semantic probe to distinguish "exact token survived" from "the underlying task fact survived."

Canary survival and semantic survival remain separate metrics.

A positive canary score alone is not a software-engineering efficacy result.

## 5. Fixture validity requirements

A valid B-vs-C survival experiment must create enough distance and interference that the comparison is not trivial, without synthetic filler or outcome-based tuning.

Pre-register and enforce:

- high-value state is discovered and recorded in an early phase;
- at least **12 substantive turns** occur after state recording and before `/compact`;
- the final **8 pre-compact turns** do not reread or echo survival canaries;
- intervening work is real investigation/implementation/verification work;
- the compaction boundary is fixed before arm outcomes are observed;
- A/D have no WORKING_STATE before compact;
- B/C have WORKING_STATE with the complete canary set before compact;
- one and only one scripted compaction boundary is observed;
- probe tools are disabled.

v1 and v2 remain historical invalid pilots. Do not edit them in place or reinterpret their scores as efficacy evidence.

## 6. Claude Code isolation controls

### Version and model

Pin and record:

- Claude Code version;
- resolved model identifier from `system/init`;
- target initial commit;
- fixture source commit;
- prompt hashes;
- fixed compact boundary.

Abort on version/model drift during a scored run.

### Native Auto Memory

Claude Code Auto Memory is a separate persistence channel and is enabled by default in current Claude Code.

All controlled runs must set:

```text
CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
```

and record that control in provenance.

No new v3 dry run should be treated as valid until this control is implemented in the runner.

### Scripted host configuration

Claude Code recommends `--bare` for reproducible scripted calls because it avoids automatic discovery of user/project hooks, skills, plugins, MCP, Auto Memory, and CLAUDE.md.

However, bare mode also changes authentication behavior. Do not switch a scored series from non-bare to bare mid-experiment. Prefer bare mode only once a reproducible authentication path is established; until then explicitly disable Auto Memory and record configuration provenance.

### Auto compaction / updater

For the fixed-boundary mechanism fixture:

- `DISABLE_AUTO_COMPACT=1`
- `DISABLE_AUTOUPDATER=1`

Observe `system/compact_boundary` directly for every arm rather than inferring compaction from Context Guard hooks.

## 7. Per-run measurements

Record the following without turning each item into a separate hypothesis:

### Mechanism outcomes

- exact canary survival;
- semantic-probe score;
- state-manipulation validity;
- compaction-boundary validity;
- Context Guard hook errors;
- recovery-context size.

### Cost / efficiency

- hook duration where available;
- recovery-context chars;
- compact pre/post token observations where Claude Code exposes them;
- total wall time;
- turn/tool counts;
- repeated work / rereads where deterministically measurable.

### Task outcome

- visible tests;
- hidden acceptance tests;
- final repository state / evaluator result.

Task outcome from RouteForge is diagnostic only. External H3 claims require a real-world benchmark.

## 8. External validation after RouteForge

Do not build a large bespoke benchmark suite before using available external evidence.

After RouteForge v3 is valid and the controlled mechanism comparison is worth pursuing, pre-register a separate protocol on a public repository-level SWE benchmark.

Candidate families, subject to environment/licensing/reproducibility review at the time of implementation:

- SWE-bench / SWE-bench Verified;
- SWE-Bench Pro or its verified public subset;
- RoadmapBench for longer multi-target version-upgrade tasks.

The external protocol should compare a strong native baseline against the minimal Context Guard increment, keep the model/version fixed, and inject compaction at a pre-registered boundary where the benchmark harness permits it.

## 9. Decision rules

Do not proceed to FTS, embeddings, vector databases, knowledge graphs, or another LLM summarizer merely because such systems exist in the literature.

Richer retrieval is justified only if the minimal mechanism establishes a measurable need.

### Stop / simplify

- If valid B vs C shows no practically useful increment, do not add retrieval complexity to rescue the hypothesis.
- If survival improves but external task outcome does not, describe Context Guard as a memory-preservation aid rather than a demonstrated SWE-performance improvement.
- If benefit exists but operational cost is excessive, revise budgets/triggering before adding retrieval.

### Continue

If rehydration shows a useful incremental mechanism effect **and** external task evidence suggests real outcome value, then richer retrieval can be evaluated one component at a time with the same ablation discipline.

## 10. Provenance and interpretation

Store enough provenance to reproduce the comparison, but do not publish real project transcripts or sensitive state.

A benchmark result is interpretable only if:

- the fixture/protocol was frozen before scored arm outcomes;
- arm manipulation checks passed;
- model/version/config did not drift;
- hidden evaluators remained hidden;
- native persistence channels were controlled;
- invalid pilots are not pooled with valid scored runs.

See [[research-positioning]] for the prior-art rationale behind this reduced scope.