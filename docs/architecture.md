---
title: Architecture
date: 2026-09-11
tags: [architecture, compaction, memory]
status: draft
type: reference
---

# Architecture (v0.1)

仕様の source of truth は `SPEC.md`。現行 Claude Code の実測 schema は [[compatibility]]。
運用手順は [[operations]]。

## 1. 何を解いているか

Claude Code の context compaction は、長いセッションの transcript を要約に置き換える。
要約は「会話として何が起きたか」を保つが、**次の一手を決めるのに必要な作業状態**は
確率的に落ちる。落ちやすいのは次の種類の情報である。

- 何を達成しようとしていたか（goal と acceptance criteria）
- なぜこの設計にしたか（rationale）
- 何を試して棄却したか（rejected approaches）
- まだ直っていない failure
- 次に打つべき具体的な手

v0.1 はこれらを **compaction の外**（filesystem）に置き、compaction 後に
**最小限だけ**注入し直す。native compaction を置き換えない。二重要約もしない。

## 2. なぜ code / diff / log を durable memory にしないのか

> [!important]
> これは v0.1 の中心的な設計判断である。

### 2.1 コードは既に永続化されている

`git` と filesystem が既にコードの正確な最新状態を持っている。
memory に写しを持つと、**同じ事実の情報源が 2 つになる**。

### 2.2 写しは必ず古くなる（stale memory 問題）

memory に保存した瞬間、その写しは時間とともに現実と乖離する。
compaction 後の Claude が「記憶しているコード」と「現在のファイル」を突き合わせたとき、
どちらが正しいかを判断する手段はない。
そして **古い写しは、情報が無い状態より有害**である。無ければ読み直すが、
あれば読み直さずに誤った前提で編集する。

だから recovery context は毎回「filesystem を source of truth として扱え」と明示し、
git state は checkpoint の値ではなく **rehydration 時に再計算**する。

### 2.3 コストの非対称性

- コード本文を memory から復元する価値 ≒ `Read` 1 回分
- コード本文を memory に置くコスト = active context の恒久的な占有

一方で「なぜその設計にしたか」は filesystem のどこにも書かれていない。
**再取得が不可能な情報だけが durable memory に値する**。

### 2.4 tool output / log は署名が長く価値が短い

成功した command の出力、繰り返しのファイル読み、冗長な tool log は、
量が大きく、かつ決定が済んだ時点で価値がほぼ 0 になる。
これらは保存せず、compaction に捨てさせる（root `CLAUDE.md` の Compact Instructions）。

### 2.5 transcript 本文を触らないこと自体が設計

transcript を解析すれば「もっと賢い」抽出ができそうに見えるが、v0.1 はしない。理由:

- transcript には secret / 大量のコード / 第三者のデータが混入する。
  複製すれば漏洩面が増える
- 解析は LLM を要求し、native compaction と二重要約になる（SPEC §2.3）
- 解析は非決定的になり、[[benchmark-plan]] の baseline が測れなくなる

`transcript_path` は **pointer として記録するだけ**で、開かない。

## 3. コンポーネント

```text
                      Claude Code
   PreCompact │      SessionStart(compact) │      PostCompact
              ▼                            ▼                 ▼
           hooks.handle_pre_compact  handle_session_start  handle_post_compact
              │                            │                 │
              │  ┌─────────────────────────┼─────────────────┐
              ▼  ▼                         ▼                 ▼
           state.py                   git_state.py       storage.py
       WORKING_STATE の読取/hash    branch/HEAD/status   safe path / atomic write
       budget 内への決定的切り捨て    （best-effort）       events.jsonl append
```

- `cli.py` — stdin JSON を読み、subcommand に振り分け、**全ての例外を吸収して exit 0**
- `hooks.py` — 3 つの hook handler。副作用の順序と何を返すかだけを決める
- `state.py` — WORKING_STATE の読取・hash・budget 管理・recovery context の組み立て
- `git_state.py` — git の best-effort 収集。非 git でも `is_repo: False` を返して通す
- `storage.py` — path の安全性、atomic write、event append
- `models.py` — payload / checkpoint の薄い型

## 4. データフロー

### PreCompact（書くだけ、返さない）

1. payload から `session_id` / `trigger` / `cwd` / `transcript_path` を取る
2. 現在の git state を収集する（best-effort）
3. WORKING_STATE を読み、文字数と SHA-256 を取る
4. `checkpoint.json` / `checkpoint.md` を atomic に書く
5. `pre_compact` イベントを append する
6. **stdout に何も出さない**。compaction に一切干渉しない

### SessionStart(compact)（読んで返す）

1. `source == "compact"` でなければ即 no-op（allow-list）
2. WORKING_STATE を読む（無ければ最小メッセージのみ）
3. git state を**再計算**する（checkpoint の値は使わない）
4. recovery instruction + state + git を組み立て、**9,000 chars 以下**に収める
5. `hookSpecificOutput.additionalContext` で返す
6. `rehydrate` イベントを append する

### PostCompact（保存するだけ）

1. `compact_summary` を `compact-summary.md` に**一字一句そのまま**保存する
2. `timestamp` / `trigger` / `summary_chars` / `summary_sha256` を記録する
3. **Claude に返さない**。native summary は既に context に入っているので、
   再注入すれば同じ内容が二重に active context を占める

## 5. Budget 設計

| 区分 | 上限 | 根拠 |
|---|---|---|
| WORKING_STATE | 6,000 chars | 人が保守できる上限。これを超える state は圧縮されていない |
| git state | 2,000 chars | branch / HEAD / status --short が収まる |
| recovery instruction | 1,000 chars | 固定文 |
| **合計** | **9,000 chars** | compaction 直後の active context を小さく保つ |

超過時は**失敗せず決定的に切り捨てる**。切り捨ては先頭を残す
（`# Goal` と `# Acceptance criteria` が WORKING_STATE の先頭にあるため、
切り捨てても「何をしているか」は残る）。切り捨てたことは明示マーカーで示し、
full file への path を併記して、必要なら Claude が自分で読めるようにする。

## 6. Fail-open の設計

hook は Claude Code の作業経路に割り込む。**壊れた hook が compaction を止めるのは最悪**である。

- PreCompact は exit code 常に 0。`decision` / `continue: false` / `stopReason` を出さない
- 全 handler は例外を捕捉し、可能なら `hook_error` イベントを書いてから 0 で抜ける
- 書き込み先が使えない（`.claude/context-guard` が通常ファイル、権限なし、`cwd` が存在しない）
  場合も 0 で抜ける
- 未知の subcommand でも 0 で抜ける（stale な `settings.json` が compaction を壊さないため）

**トレードオフ**: hook が黙って失敗するため、checkpoint が無いことに気づきにくい。
これは `events.jsonl` の `hook_error` と `doctor` で観測可能にすることで補う。

## 7. Path safety

- `session_id` は hook JSON 由来の**信用できない入力**である
- ディレクトリ名に使う前に sanitize し、`../` / 絶対パス / 空文字 / 非文字列を無害化する
- 書き込み先は解決後に `guard_root` 配下であることを確認する。外れたら例外にし、呼び出し側が fail-open する
- git は引数配列で呼ぶ。`shell=True` を使わない。hook JSON の値をコマンドとして実行しない

## 8. v0.1 が意図的に持たないもの

vector DB / embeddings / FTS / SQLite / knowledge graph / event sourcing reducer /
transcript の意味解析 / 自動 LLM handoff / 自動 semantic compaction / daemon / UI / MCP。

理由は単純で、**まだ測っていない**からである。
これらは [[benchmark-plan]] で v0.1 に対する改善が示せた段階で初めて検討する。
