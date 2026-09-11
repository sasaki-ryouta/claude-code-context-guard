# Claude Code Context Guard — v0.1 Specification

## 1. Purpose

Claude Codeのcontext compaction前後で、長時間coding taskに必要な高価値な作業状態を外部化し、compaction後に最小限だけ再注入する。
目的は「巨大contextを検索可能にすること」ではない。

v0.1の目的は以下である。

1. compactionによる重要な作業状態の消失を軽減する
2. compaction後のactive contextを小さく保つ
3. code/filesystemをsource of truthとして扱う
4. state / decisions / failures / next actions / pointersだけをdurable stateとして保持する
5. native Claude Code compactionを置き換えない
6. 後続のbenchmark / FTS / vector / graph実験のための観測基盤を作る

## 2. Design principles

### 2.1 Filesystem is source of truth

コード本文、diff全文、ログ全文、tool output全文をmemoryとして保存・再注入しない。
必要な場合はClaudeが現在のfilesystemから再読する。

保存対象は主に以下。

- current goal
- acceptance criteria
- current phase
- architectural / implementation decisions
- rationale
- unresolved failures
- rejected approaches when still relevant
- next action
- relevant file/symbol/test/ADR pointers

### 2.2 Keep active memory small

compaction後に再注入するcontextは最大9,000 charactersとする。

内訳の目安:

- WORKING_STATE: 最大6,000 chars
- current git state: 最大2,000 chars
- recovery instructions: 最大1,000 chars

通常はこれより小さくする。

### 2.3 No second LLM summarization in v0.1

PreCompactで別のLLMを呼び出してtranscriptを再要約しない。
Claude Code native compactionと二重要約しない。
v0.1ではdeterministicなcheckpointのみ行う。

### 2.4 Fail open

Hook障害によってClaude Codeの作業やcompactionを止めない。

特にPreCompactは:

- compactionをblockしない
- exit code 2を返さない
- `decision: block`を返さない

Hook内部で例外が発生しても可能な限りログを残してexit 0する。

### 2.5 Project-local

v0.1はproject-local implementationとする。
ユーザーの `~/.claude/settings.json` を自動変更しない。
global install、daemon、external serviceは導入しない。

## 3. Runtime

Python 3.11+。
Runtime dependencyはPython standard libraryのみ。

以下を禁止する。

- database
- embedding API
- vector database
- Neo4j
- external LLM call
- network access
- shell=True
- transcript全文の解析

Test frameworkも可能ならstdlib `unittest` を使用する。

## 4. Directory structure

以下を基本構成とする。

```text
claude-code-context-guard/
├── README.md
├── SPEC.md
├── CLAUDE.md
├── pyproject.toml
├── .gitignore
├── .claude/
│   ├── settings.example.json
│   └── context-guard/
│       └── WORKING_STATE.template.md
├── src/
│   └── context_guard/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── hooks.py
│       ├── state.py
│       ├── git_state.py
│       ├── storage.py
│       └── models.py
├── tests/
│   ├── fixtures/
│   │   ├── pre_compact.json
│   │   ├── session_start_compact.json
│   │   └── post_compact.json
│   ├── test_pre_compact.py
│   ├── test_session_start.py
│   ├── test_post_compact.py
│   ├── test_state_budget.py
│   └── test_fail_open.py
└── docs/
    ├── architecture.md
    ├── operations.md
    ├── benchmark-plan.md
    └── roadmap.md
```

Runtime時にはtarget project内に以下を生成する。

```text
.claude/context-guard/
├── WORKING_STATE.md
└── sessions/
    └── <safe-session-id>/
        ├── checkpoint.json
        ├── checkpoint.md
        ├── compact-summary.md
        └── events.jsonl
```

runtime stateはデフォルトでgitignoreする。

## 5. WORKING_STATE contract

`WORKING_STATE.md` はClaudeが作業中に維持するexplicit working memoryである。

フォーマット:

```md
# Goal

現在達成しようとしている結果。

# Acceptance criteria

- 完了条件

# Current phase

Investigation | Planning | Implementation | Verification | Review

# Decisions

- Decision
  - Why:
  - Affects:

# Current failures

- Failure:
  - Evidence:
  - Suspected cause:

# Next

- 次に実行すべき具体的action

# Pointers

- file:
- symbol:
- test:
- ADR:
- issue:

# Notes

必要な場合のみ。
```

ルール:

- 6,000 characters以内を目標とする
- source code全文を書かない
- command output全文を書かない
- diff全文を書かない
- resolved failureは削除する
- superseded decisionは削除または明示的にsupersededとする
- filesystemから再取得可能な情報を複製しない
- secret/token/passwordを書かない

Claudeは毎turn更新しない。
以下のsemantic boundaryで更新する。

- investigation完了
- plan確定
- 重要decision確定
- implementation phase移行
- root cause判明
- major hypothesis棄却
- verification phase移行
- task goal変更
- `/compact` を推奨する直前

## 6. Compact Instructions

root `CLAUDE.md` に以下の意味を持つ `# Compact Instructions` セクションを置く。

Preserve:

- current user goal
- acceptance criteria
- current phase
- unresolved next step
- architectural and implementation decisions
- rationale for non-obvious decisions
- relevant rejected approaches
- modified/relevant file pointers
- unresolved failing tests/errors
- important invariants and constraints
- ADR/issue/test/symbol pointers

Discard or aggressively compress:

- verbose tool output
- successful command output
- repeated file reads
- superseded plans
- resolved hypotheses
- resolved failures
- long source excerpts
- information that can cheaply be reread from the filesystem

After compaction:

- treat current filesystem as authoritative
- do not trust remembered source snapshots over current files
- reread relevant files before making non-trivial edits

## 7. Hook behavior

### 7.1 PreCompact

Supported trigger:

- manual
- auto

Input is read as JSON from stdin.

Capture:

- session_id
- trigger
- cwd
- transcript_path
- UTC timestamp
- git branch
- git HEAD
- `git status --short`
- WORKING_STATE snapshot
- WORKING_STATE SHA-256

Write:

```text
sessions/<session-id>/checkpoint.json
sessions/<session-id>/checkpoint.md
sessions/<session-id>/events.jsonl
```

Do NOT:

- invoke LLM
- parse the transcript body
- store full git diff
- modify WORKING_STATE
- block compaction
- emit context back to Claude

All writes should use safe paths and preferably atomic replacement.
Malformed input or non-git directory must not break compaction.

### 7.2 SessionStart: compact

Only act when:

```json
{
  "source": "compact"
}
```

Construct recovery context from:

1. current WORKING_STATE.md
2. fresh current git state
3. short recovery instruction

Do not use stale git information from the checkpoint when current git state can be recomputed.

Recovery context should clearly say:

```text
This is external working state restored after context compaction.

Treat the current filesystem as source of truth.
The state below contains goals, decisions, unresolved failures, next actions,
and pointers; it is not a substitute for rereading relevant source files.
```

Return using Claude Code `SessionStart` `hookSpecificOutput.additionalContext`.
Total `additionalContext` must remain <= 9,000 characters.

If WORKING_STATE exceeds its budget:

- do not fail
- deterministically truncate
- include an explicit marker
- include the path to the full file

If no state exists:

- inject only a minimal recovery message and current git state
- do not invent state

### 7.3 PostCompact

Read:

- session_id
- trigger
- compact_summary
- cwd
- transcript_path

Persist:

```text
compact-summary.md
events.jsonl
```

Record metadata:

- timestamp
- trigger
- compact summary length
- SHA-256 of compact summary

PostCompact must not attempt to modify the completed compaction.
Do not reinject its summary into Claude.

## 8. Git collection

Git inspection is best-effort.

Capture only:

- repository root
- branch
- HEAD
- `git status --short`

Do not capture full patch/diff in v0.1.
Use subprocess argument arrays.
Never use shell interpolation.
Non-git projects must continue functioning.

## 9. Security

Mandatory:

- sanitize session_id before using it as a directory name
- prevent `../` path traversal
- ensure generated files remain under `.claude/context-guard`
- no `shell=True`
- no execution of data read from hook JSON
- no network requests
- no transcript copying
- no secrets extraction
- do not automatically commit runtime memory
- do not modify user-global Claude settings

## 10. Hook configuration example

Provide `.claude/settings.example.json`.

It must configure:

- PreCompact matcher: `manual|auto`
- SessionStart matcher: `compact`
- PostCompact matcher: `manual|auto`

Commands should execute this repository's Python entrypoint.
The exact syntax must be verified against the locally installed Claude Code version before finalizing.
Do not silently modify the user's global settings.

## 11. Auto-compaction threshold

The memory system must NOT depend on a particular token threshold.

Recommended operating policy:

- semantic/manual compaction at meaningful phase boundaries
- automatic compaction acts as a safety net

If the locally installed Claude Code build exposes a supported configurable auto-compaction window, document 400k as the initial experimental safety threshold.
Do not assume undocumented setting names.

Before documenting an exact configuration key:

1. inspect local Claude Code version
2. verify the supported local configuration mechanism
3. cite/link the official relevant documentation in docs/operations.md

If no supported setting exists in the installed build, omit it.

## 12. Semantic compaction policy

v0.1 does NOT automatically decide when to invoke `/compact`.

Instead CLAUDE.md should tell Claude to recommend a manual `/compact` to the user when:

- a major investigation phase has completed
- a plan has stabilized
- a major implementation unit is complete
- debugging has converged and verification is starting
- a large volume of obsolete tool output has accumulated

Before recommending `/compact`, update WORKING_STATE.md.

Token threshold is therefore a safety mechanism, not the primary semantic boundary mechanism.

## 13. Observability

Each session maintains append-only `events.jsonl`.

Minimum event types:

```text
pre_compact
post_compact
rehydrate
hook_error
```

Each event contains where applicable:

- timestamp
- session_id
- trigger/source
- state size
- state hash
- summary size
- summary hash
- branch
- HEAD

Never store entire transcript in events.

## 14. CLI

Implement:

```text
python -m context_guard pre-compact
python -m context_guard session-start
python -m context_guard post-compact
python -m context_guard doctor
```

`doctor` checks:

- Python version
- project root
- WORKING_STATE existence
- state character budget
- hook configuration presence
- executable/importability
- current git status availability

It must not modify configuration.

## 15. Tests

All hook handlers must be testable without launching Claude Code.
Use stdin fixtures.

Required cases:

PreCompact

- valid manual input
- valid auto input
- missing WORKING_STATE
- non-git cwd
- malformed JSON
- malicious session_id/path traversal attempt

SessionStart

- source=compact
- other source => no recovery injection
- missing WORKING_STATE
- state under budget
- state over budget
- missing git repository
- output <= 9,000 chars

PostCompact

- summary saved exactly
- metadata/hash correct
- missing compact_summary handled safely
- malformed input fails open

General

- runtime has no third-party dependencies
- no writes outside context-guard root
- hook failure never intentionally blocks compaction

## 16. Acceptance criteria

v0.1 is complete when:

1. all tests pass
2. hook handlers work from JSON fixtures
3. PreCompact creates deterministic checkpoint artifacts
4. SessionStart(compact) injects <=9,000 chars
5. PostCompact persists Claude native summary
6. malformed hook input does not block compaction
7. non-git projects still work
8. session-id path traversal is impossible
9. no runtime network/LLM/database dependency exists
10. README contains a 5-minute manual setup procedure
11. `doctor` can validate an installation
12. architecture document explains why code/logs are not durable memory
13. benchmark plan exists for future comparison against native Claude Code

## 17. Explicit non-goals for v0.1

DO NOT implement:

- embeddings
- vector search
- FTS/BM25
- SQLite
- knowledge graph
- event-derived state reducer
- transcript semantic extraction
- automatic LLM handoff generation
- automatic semantic `/compact`
- fine-tuning
- daemon/background process
- cloud service
- UI
- MCP server
- Claude Skill/plugin packaging
- global installer

These belong to later experiments only after v0.1 has benchmark data.

## 18. Roadmap

v0.2 — benchmark + semantic boundaries

- native compaction baseline
- threshold sweep
- WORKING_STATE ablation
- phase-boundary compaction experiments
- compaction survival metrics

v0.3 — lexical retrieval

- structured episodes
- SQLite FTS/BM25
- retrieval precision measurement

v0.4 — semantic retrieval

- embeddings
- hybrid retrieval
- reranking
- compare incremental value over FTS

v0.5 — causal/state memory

- decision/file/test relationships
- stale-memory handling
- graph/event-sourced approaches

Every feature after v0.1 must demonstrate measurable improvement before becoming part of the recommended default architecture.

## 19. Primary research question

The broader project should eventually answer:

How much of the performance degradation caused by long-running Claude Code sessions can be avoided using project-local, training-free context management while keeping the active working context small?

v0.1 is infrastructure for answering that question, not the final memory architecture.
