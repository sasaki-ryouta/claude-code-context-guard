---
title: Native-first working-state setup
date: 2026-09-15
tags: [operations, claude-code, working-state, configuration]
status: recommended-baseline
type: reference
---

# Native-first working-state setup

The H1 pilot established one bounded result: on the frozen RouteForge fixture, maintained working state alone was already sufficient in most scored runs, and Context Guard rehydration did not show the pre-registered directional consistency required to justify external validation.

That result does **not** prove that rehydration is generally useless, and it does not measure software-engineering outcomes. The recommendations below are therefore split into two layers:

- **evidence-backed conclusion:** do not make Context Guard rehydration hooks the default merely on the strength of H1;
- **operational recommendation:** start with a small project-local working state, ordinary Claude Code persistence features, and semantic compaction discipline; add Context Guard only when its checkpoint/reinsertion behavior solves an observed problem.

For ordinary use, the suggested baseline is:

1. keep Claude Code Auto Memory enabled unless you have a separate reason to disable it;
2. put cross-project working habits in the user-level `~/.claude/CLAUDE.md`;
3. keep current-task handoff state project-local and checkout-local;
4. use native auto-compaction as a safety net rather than the only compaction strategy;
5. update working state at semantic boundaries and before a deliberate `/compact`;
6. add Context Guard hooks only when automatic reinsertion or inspectable compaction checkpoints solve a concrete problem you have observed.

This is an operational recommendation, not a claim that one compaction threshold, one memory layout, or one persistence combination is universally optimal.

## 1. Global policy, local state

A useful split is:

| concern | location | scope |
|---|---|---|
| recurring personal workflow rules | `~/.claude/CLAUDE.md` | all projects |
| project-specific opt-in | `CLAUDE.local.md` | one checkout / user |
| current-task handoff state | `WORKING_STATE.local.md` | one checkout / user |
| project architecture/build/test rules | project `CLAUDE.md` | one project / shared |
| durable cross-session learnings/preferences | Auto Memory | native Claude Code memory |
| automatic checkpoint/reinsertion | Context Guard hooks | optional per project |

Do **not** use one global working-state file for every repository. Goals, decisions, failures, and next actions must stay associated with the project and checkout that produced them.

Also avoid duplicating the same material across persistence channels. A practical ownership boundary is:

- `WORKING_STATE.local.md`: volatile state needed to resume the current task;
- Auto Memory: durable conventions, preferences, and learnings that remain useful after the current task ends.

## 2. Install the global working-state policy

Copy [`examples/global-CLAUDE.md`](../examples/global-CLAUDE.md) into your user-level Claude instructions, either as the whole `~/.claude/CLAUDE.md` or merged into an existing file.

The global policy intentionally describes **how** to maintain state without hard-coding a repository path. That prevents Claude from creating task-state files in every temporary checkout or repository you inspect.

## 3. Opt a project in

For a project where explicit working state is useful:

1. copy [`examples/project-CLAUDE.local.md`](../examples/project-CLAUDE.local.md) to `CLAUDE.local.md`;
2. copy the existing [`WORKING_STATE.template.md`](../.claude/context-guard/WORKING_STATE.template.md) to `WORKING_STATE.local.md`;
3. keep both files out of Git.

Example:

```bash
cp /path/to/claude-code-context-guard/examples/project-CLAUDE.local.md CLAUDE.local.md
cp /path/to/claude-code-context-guard/.claude/context-guard/WORKING_STATE.template.md WORKING_STATE.local.md
printf '\nCLAUDE.local.md\nWORKING_STATE.local.md\n' >> .gitignore
```

Use repository-local ignore conventions if your project has a different policy. The important invariant is that user-specific instructions and volatile task state do not become shared project history by accident.

For the native-first baseline, `WORKING_STATE.local.md` is intentionally outside `.claude/`. This avoids making ordinary state maintenance depend on configuration-directory write permissions. If you later install Context Guard, use its supported runtime path instead:

```text
.claude/context-guard/WORKING_STATE.md
```

Context Guard's own setup documents the required ignore rules and validates them with `doctor`.

The core state fields are:

- Goal
- Acceptance criteria
- Current phase
- Decisions
- Current failures
- Next
- Pointers
- Notes only when necessary

The state is a pointer-rich handoff, not a transcript. Prefer file/symbol/test/issue references over copied source, diffs, or command output.

## 4. Compaction policy

Use native auto-compaction as a safety net. This project has **not** established an optimal numeric threshold or a universal compaction window.

For high-value work, prefer semantic boundaries:

1. finish investigation, planning, a major implementation unit, or debugging;
2. update the working state;
3. run `/compact` deliberately when the accumulated context is no longer worth carrying;
4. after compaction, treat the filesystem as authoritative and reread the files needed for the next non-trivial edit.

This keeps durable intent separate from disposable tool output.

## 5. Auto Memory

For normal interactive work, leave Auto Memory enabled unless you have a separate reason to disable it.

`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` was used by the benchmark to remove a persistence channel and isolate causality. It is **not** the default daily-use recommendation.

Likewise, `--setting-sources project` was a benchmark isolation control for user/local settings. The benchmark also disabled Auto Memory separately and verified the actually observed host surface per run. Do not treat `--setting-sources project` by itself as proof that every host-level persistence or extension surface has been removed.

## 6. What H1 actually supports

The scored H1 pilot compared maintained working state alone with the same maintained state plus Context Guard rehydration. It disabled Auto Memory and native auto-compaction, used a fixed compaction boundary, and measured state survival rather than coding outcomes.

The supported conclusion is narrow: this fixture did not provide the pre-registered evidence needed to promote rehydration hooks as the default or to spend external-validation budget.

The following are **not** H1 findings:

- that Auto Memory improves outcomes;
- that semantic manual `/compact` is superior to every alternative;
- that native auto-compaction is optimally configured by any particular threshold;
- that rehydration is redundant in general;
- that this setup improves software-engineering outcomes.

Those parts of this page are operational defaults chosen to minimize complexity and duplicated persistence, not causal claims from the pilot.

## 7. When to add Context Guard hooks

Do not add the three hooks merely because explicit state exists. The scored pilot found maintained state alone was already sufficient in most runs of its fixture.

Add Context Guard when one of these is specifically valuable:

- you want deterministic pre-compaction checkpoints;
- you want the maintained state automatically reinserted after compaction;
- you want inspectable per-compaction archives for debugging or audit;
- you have observed recurring post-compaction failures despite accurate maintained state and want to test whether reinsertion addresses them.

If you install Context Guard, use the full supported three-hook wiring and run `doctor`; do not assemble a partial hook set casually.

## 8. Avoid stacked restoration channels

Session-start restoration is powerful but easy to duplicate. If you use Auto Memory, a custom session-summary plugin, Context Guard, and another restore hook at the same time, stale or redundant context can accumulate.

Before adding a restoration hook, inspect user-level and project-level `SessionStart` hooks and plugins. Prefer one clearly owned mechanism per class of state and verify what actually loads into the session.

For ordinary native-first use, keep the ownership boundary explicit:

```text
Auto Memory          = durable cross-session learnings/preferences
WORKING_STATE.local  = volatile current-task handoff
Context Guard        = optional automatic checkpoint/reinsertion
```

## 9. Suggested baseline

For most users, start with the operationally simpler configuration below while keeping the H1 evidence boundary in mind:

```text
user-level CLAUDE.md policy
+ Auto Memory enabled
+ checkout-local small WORKING_STATE.local.md
+ semantic manual /compact when useful
+ native auto-compaction as a safety net
+ no Context Guard hooks by default
```

Then add Context Guard only for checkpointing/reinsertion needs you can name and observe.

See [`docs/h1-pilot-results.md`](h1-pilot-results.md) for the measured result and [`docs/h1-pilot-gate-verdicts.md`](h1-pilot-gate-verdicts.md) for the configuration-contamination failure modes discovered during the experiment.