---
title: Architecture
date: 2026-09-11
tags: [architecture, compaction, memory]
status: operational-baseline
type: reference
---

# Architecture (v0.1.1)

`SPEC.md` が基本仕様、`docs/compatibility.md` が installed Claude Code との compatibility record。v0.1.1 は v0.1 の機能範囲を広げず、project-root resolution、履歴 provenance、doctor、CI、privacy wording を operational hardening した patch release である。

## 1. 解く問題

Claude Code の native compaction で落ち得る current goal / acceptance criteria / phase / decision+rationale / rejected approach / unresolved failure / next action / pointer を explicit `WORKING_STATE.md` に置き、compaction 後に bounded context として戻す。native compaction は置き換えず、PreCompact で別 LLM による二重要約もしない。

## 2. Source of truth

source code、diff、test log、command output の全文は durable memory にしない。コードには既に filesystem という最新 source of truth があり、memory copy は stale snapshot を作る。

一方、decision rationale や rejected hypothesis は filesystem から安価に復元できないため `WORKING_STATE.md` に保持する。

> 再取得可能な raw data は pointer にし、再取得困難な reasoning state だけを durable にする。

## 3. Stable project root

Hook payload の `cwd` は `cd` によって変わり得るため persistence root には直接使わない。

resolution order:

1. valid `CLAUDE_PROJECT_DIR`
2. current cwd の Git worktree root
3. current cwd

CLI は `CLAUDE_PROJECT_DIR` を internal payload field にコピーして handler へ渡す。checkpoint には current `cwd` と resolved `project_root` を両方残す。

## 4. Data flow

```text
WORKING_STATE.md
      |
PreCompact
  +-- curated state + current git state
  +-- allocate sequence
  +-- archive checkpoint + latest checkpoint
      |
native compact
      |
PostCompact
  +-- native summary latest + archive
      |
SessionStart(compact)
  +-- current WORKING_STATE + recomputed git state
  +-- <= 9,000 chars additionalContext
```

Hook order は Claude Code が決める。隣接 event が欠けても fail-open する。

## 5. Per-compaction provenance

```text
sessions/<session-id>/
├── checkpoint.json
├── checkpoint.md
├── compact-summary.md
├── events.jsonl
└── compactions/000001/
    ├── checkpoint.json
    ├── checkpoint.md
    └── compact-summary.md
```

top-level files は latest view。`compactions/NNNNNN/` は benchmark と incident inspection の provenance で、event hash だけでは復元できない compaction 時点の state を保持する。

## 6. Context budget

| component | cap |
|---|---:|
| WORKING_STATE | 6,000 chars |
| git state | 2,000 chars |
| total additionalContext | **9,000 chars** |

Oversized state は deterministic に head truncateし、marker + full local pathを残す。

## 7. Fail-open

Hook CLI は malformed input / storage error / git error でも exit 0 を基本とする。PreCompact は blocking decision を出さない。observability failure は valid rehydration を潰さない。`doctor` のみ explicit diagnostic として non-zero を返す。

## 8. Path safety

`session_id` は untrusted input として sanitize し、runtime write は `.claude/context-guard` 配下へ制限する。Git は argument array で起動し `shell=True` を使わない。

## 9. Privacy boundary

Context Guard は transcript body、source files、command logs を secret 探索のために読まない。しかし redaction もしない。`WORKING_STATE` snapshot と native `compact_summary` は verbatim 保存されるため sensitive data を含み得る。runtime directory は local sensitive data として扱う。

## 10. Retrieval はまだ入れない

FTS/BM25、embedding、vector DB、knowledge graph、event-derived memory は baseline の task outcome 改善を測ってから一つずつ追加する。
