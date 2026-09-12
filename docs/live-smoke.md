---
title: Live Claude Code smoke test
date: 2026-09-12
tags: [operations, smoke-test, hooks]
status: live-validated
type: runbook
---

# Live Claude Code lifecycle smoke test

This runbook validates the boundary that unit tests cannot: a real Claude Code process firing `PreCompact`, `PostCompact`, and `SessionStart(source=compact)` around `/compact`.

Run it after upgrading Claude Code or Context Guard, and before calling a new combination live-validated.

Last successful run: Claude Code **2.1.245**, Python **3.13.2**, macOS Darwin **25.6.0 arm64**, Context Guard commit `fcb45fcde35b9ef3e9d81f1a4197f21defe5940f`. Detailed evidence is recorded in GitHub Issue #7 and `docs/compatibility.md`.

## Preconditions

- clean checkout of `main`
- Python 3.11+
- locally installed Claude Code
- no credentials or sensitive text in the smoke-state fixture

Record:

```bash
claude --version
python3 --version
git rev-parse HEAD
```

## 1. Prepare project-local configuration

From this repository root:

```bash
cp .claude/settings.example.json .claude/settings.json
mkdir -p .claude/context-guard
cp .claude/context-guard/WORKING_STATE.template.md .claude/context-guard/WORKING_STATE.md
```

Put distinctive, non-sensitive values in `WORKING_STATE.md`:

```md
# Goal

LIVE-SMOKE-GOAL: verify Context Guard survives a real /compact lifecycle.

# Acceptance criteria

- rehydration recalls LIVE-SMOKE-GOAL
- state remains rooted at the repository root after cd

# Current phase

Verification

# Decisions

- LIVE-SMOKE-DECISION: filesystem remains source of truth
  - Why: stale source snapshots are unsafe
  - Affects: rehydration behavior

# Current failures

- Failure: none

# Next

- LIVE-SMOKE-NEXT: inspect lifecycle artifacts after /compact

# Pointers

- file: src/context_guard/hooks.py
```

Run:

```bash
PYTHONPATH=src python3 -m context_guard doctor
```

Expected: exit code `0`, `Hook configuration: ok`, and `Runtime gitignore: ok`.

## 2. Exercise a real compaction boundary

Start Claude Code from the repository root. In the session:

1. Ask Claude to read `WORKING_STATE.md` and confirm the three `LIVE-SMOKE-*` markers.
2. Change the session working directory to a nested directory such as `src/context_guard`.
3. Ask Claude to do a small read-only inspection so the nested cwd is genuinely active from the model/tool perspective.
4. Invoke `/compact`.
5. Immediately after compaction, without manually reopening `WORKING_STATE.md`, ask Claude to state:
   - the current goal
   - the recorded decision
   - the next action

For a stronger survival check, disable file-reading/search/editing tools for the post-compact question. Pass if the three markers survive through the rehydrated context alone.

> [!note]
> Claude Code 2.1.245 was observed to keep the hook payload `cwd` at the project root even after a Bash-tool `cd`. Starting Claude Code directly from a nested directory is not equivalent: Claude Code may treat that directory as a separate project and not load the parent repository's `.claude/settings.json`. Therefore live smoke verifies the real lifecycle and root containment, while nested-payload-cwd resolution is covered deterministically by unit/handler tests.

## 3. Inspect artifacts

Back in a shell at the repository root:

```bash
find .claude/context-guard/sessions -maxdepth 4 -type f -print
find src -path '*/.claude/context-guard/*' -print
```

The second command must print nothing.

Inspect the newest session:

```bash
find .claude/context-guard/sessions -name events.jsonl -print
```

Then inspect its event log and first archive:

```bash
cat .claude/context-guard/sessions/<session-id>/events.jsonl
ls -la .claude/context-guard/sessions/<session-id>/compactions/000001/
```

Expected artifacts when the installed Claude Code build emits all lifecycle hooks:

```text
checkpoint.json
checkpoint.md
compact-summary.md
```

The relevant lifecycle events must share the same `compaction_sequence`. Record the actual order emitted by the installed Claude Code build rather than assuming an order not guaranteed by the hook contract.

For Claude Code 2.1.245, the observed order was:

```text
PreCompact -> SessionStart(source=compact) -> PostCompact
```

Do not encode this order as a runtime dependency.

For `rehydrate`, verify `context_chars <= 9000`.

## 4. Pass criteria

All of the following are required:

- `doctor` passes, including runtime Git-ignore safety for Git targets
- `/compact` succeeds normally
- `LIVE-SMOKE-GOAL`, `LIVE-SMOKE-DECISION`, and `LIVE-SMOKE-NEXT` are available immediately after compaction
- runtime files stay under the repository-root `.claude/context-guard`
- no nested `.claude/context-guard` tree is created during the root-started lifecycle
- deterministic nested-payload-cwd test remains green
- a coherent per-compaction archive exists
- relevant lifecycle events share the same `compaction_sequence`
- `context_chars <= 9000`
- no unexplained `hook_error` remains

## 5. Evidence and cleanup

Attach only non-sensitive evidence to the relevant GitHub validation issue: exact versions, relevant event lines, archive listing, and a short statement of what survived compaction. Do not paste a real project transcript or secrets.

After the smoke test, runtime artifacts may be removed:

```bash
rm -rf .claude/context-guard/sessions
rm -f .claude/context-guard/WORKING_STATE.md
rm -f .claude/settings.json
```

A successful run is evidence for the exact Claude Code version and Context Guard commit tested; it is not a blanket compatibility guarantee for future Claude Code builds.
