---
title: Roadmap
date: 2026-09-11
tags: [roadmap, planning]
status: draft
type: reference
---

# Roadmap

各段階は [[benchmark-plan]] で**測定可能な改善を示してから**推奨構成に入る。
示せなければその段階で止める。段階を飛ばさない。

## v0.1 — deterministic checkpoint（現在）

- PreCompact で working state を checkpoint する
- SessionStart(compact) で 9,000 chars 以下を再注入する
- PostCompact で native summary を永続化する
- `doctor` でインストールを検証する
- observability の基盤（`events.jsonl`）

**この段階では効果を主張しない。** 測るための基盤である。

## v0.2 — benchmark + semantic boundaries

- native compaction の baseline 測定
- threshold sweep（`autoCompactWindow` の公式文書化状況を再確認してから。[[compatibility]] 差分 2）
- WORKING_STATE ablation（arm A/B/C/D。[[benchmark-plan]] §2）
- phase-boundary compaction の実験
- compaction survival metrics の確立

v0.1 から持ち越した課題:

- session ディレクトリの retention / cleanup（v0.1 は無限に増える）
- hook 実行時間の記録
- 注入 chars の `rehydrate` イベントへの記録

## v0.3 — lexical retrieval

- structured episodes
- SQLite FTS / BM25
- retrieval precision の測定

**前提**: v0.2 で「state の再注入だけでは足りない」ことが示されていること。

## v0.4 — semantic retrieval

- embeddings
- hybrid retrieval
- reranking
- FTS に対する**増分**価値の比較

**前提**: v0.3 の FTS が測定可能な改善を示していること。
示せていないなら embeddings に進まない。

## v0.5 — causal / state memory

- decision / file / test の関係
- stale memory の扱い
- graph / event-sourced アプローチ

**前提**: v0.4 までで「検索はできるが因果が追えない」ことが具体的な失敗として観測されていること。

## 明示的に v0.1 の対象外（SPEC §17）

embeddings / vector search / FTS / BM25 / SQLite / knowledge graph /
event-derived state reducer / transcript の意味抽出 / 自動 LLM handoff /
自動 semantic `/compact` / fine-tuning / daemon / cloud service / UI /
MCP server / Claude Skill・plugin packaging / global installer
