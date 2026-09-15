---
title: Native-first working-state setup
date: 2026-09-15
tags: [operations, claude-code, working-state, configuration]
status: recommended-baseline
type: reference
---

# Native-first working-state setup

The H1 pilot did **not** establish a consistent useful increment from Context Guard rehydration over maintained working state alone. The practical default is therefore native-first:

1. keep Claude Code Auto Memory enabled for ordinary use;
2. put cross-project working habits in the user-level `~/.claude/CLAUDE.md`;
3. keep the actual task state project-local;
4. use native auto-compaction as a safety net, not as the only compaction strategy;
5. update working state at semantic boundaries and before a deliberate `/compact`;
6. add Context Guard hooks only when automatic reinsertion or inspectable compaction checkpoints solve a concrete problem you have observed.

This is an operational recommendation, not a claim that one compaction threshold or one memory layout is universally optimal.

## 1. Global policy, local state

A useful split is:

| concern | location | scope |
|---|---|---|
| recurring personal workflow rules | `~/.claude/CLAUDE.md` | all projects |
| project-specific opt-in | `CLAUDE.local.md` | one checkout / user |
| current task state | project-local `WORKING_STATE.md` | one project |
| project architecture/build/test rules | project `CLAUDE.md` | one project / shared |
| Claude-discovered durable knowledge | Auto Memory | native Claude Code memory |
| automatic checkpoint/reinsertion | Context Guard hooks | optional per project |

Do **not** use one global working-state file for every repository. Goals, decisions, failures, and next actions must stay associated with the project that produced them.

## 2. Install the global working-state policy

Copy [`examples/global-CLAUDE.md`](../examples/global-CLAUDE.md) into your user-level Claude instructions, either as the whole `~/.claude/CLAUDE.md` or merged into an existing file.

The global policy intentionally describes **how** to maintain state without hard-coding a specific repository path. That prevents Claude from creating Context Guard files in every temporary checkout or repository you inspect.

## 3. Opt a project in

For a project where explicit working state is useful, copy [`examples/project-CLAUDE.local.md`](../examples/project-CLAUDE.local.md) to `CLAUDE.local.md` and copy the existing [`WORKING_STATE.template.md`](../.claude/context-guard/WORKING_STATE.template.md) to a project-local path.

Recommended Context Guard-compatible path:

```text
.claude/context-guard/WORKING_STATE.md
```

If you do not use Context Guard hooks, another project-local path is fine; keep the schema small and consistent.

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

Use native auto-compaction as a safety net. A configured window such as `autoCompactWindow` can remain global if that is already part of your Claude Code setup, but this project has **not** established an optimal numeric threshold.

For high-value work, prefer semantic boundaries:

1. finish investigation, planning, a major implementation unit, or debugging;
2. update the working state;
3. run `/compact` deliberately when the accumulated context is no longer worth carrying;
4. after compaction, treat the filesystem as authoritative and reread the files needed for the next non-trivial edit.

This keeps durable intent separate from disposable tool output.

## 5. Auto Memory

For normal interactive work, leave Auto Memory enabled unless you have a separate reason to disable it.

`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` was used by the benchmark to remove a second persistence channel and isolate causality. It is **not** the default daily-use recommendation.

Likewise, benchmark isolation flags such as `--setting-sources project` existed to remove host-level plugins, MCP servers, and user hooks from experimental arms. They are not required for ordinary use.

## 6. When to add Context Guard hooks

Do not add the three hooks merely because explicit state exists. The scored pilot found maintained state alone was already sufficient in most runs of its fixture.

Add Context Guard when one of these is specifically valuable:

- you want deterministic pre-compaction checkpoints;
- you want the maintained state automatically reinserted after compaction;
- you want inspectable per-compaction archives for debugging or audit;
- you have observed recurring post-compaction failures despite accurate maintained state and want to test whether reinsertion addresses them.

If you install Context Guard, use the full supported three-hook wiring and run `doctor`; do not assemble a partial hook set casually.

## 7. Avoid stacked restoration channels

Session-start restoration is powerful but easy to duplicate. If you use Auto Memory, a custom session-summary plugin, Context Guard, and another restore hook at the same time, stale or redundant context can accumulate.

Before adding a restoration hook, inspect user-level and project-level `SessionStart` hooks and plugins. Prefer one clearly owned mechanism per class of state and verify what actually loads into the session.

## 8. Suggested baseline

For most users starting from the H1 pilot evidence:

```text
user-level CLAUDE.md policy
+ Auto Memory enabled
+ project-local small WORKING_STATE
+ semantic manual /compact when useful
+ native auto-compaction as a safety net
+ no Context Guard hooks by default
```

Then add Context Guard only for checkpointing/reinsertion needs you can name and observe.

See [`docs/h1-pilot-results.md`](h1-pilot-results.md) for the measured result and [`docs/h1-pilot-gate-verdicts.md`](h1-pilot-gate-verdicts.md) for the configuration-contamination failure modes discovered during the experiment.
