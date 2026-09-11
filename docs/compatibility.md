---
title: Claude Code compatibility
date: 2026-09-11
tags: [compatibility, hooks, claude-code]
status: verified
type: reference
---

# Claude Code compatibility (v0.1)

検証対象ビルド: **Claude Code 2.1.245** (`claude --version`)
検証方法:

1. ローカルインストール済みバイナリ
   (`@anthropic-ai/claude-code-darwin-arm64/claude`) の埋め込み文字列から、
   hook payload を生成している実コードを直接確認
2. 現行公式ドキュメント <https://code.claude.com/docs/en/hooks>
3. 現行公式ドキュメント <https://code.claude.com/docs/en/settings>

> [!note]
> ローカルビルドと公式ドキュメントが一致した項目は [[architecture]] / [[operations]] で前提として扱う。
> SPEC と現行仕様が衝突した項目のみ、本ファイルに差分と採用判断を記録する。

## 1. 確認できた現行 hook schema

### PreCompact (input, stdin JSON)

バイナリ内の生成コード:

```text
hook_event_name:"PreCompact",trigger:t.trigger,custom_instructions:t.customInstructions
```

共通フィールドと合わせて:

| field | 備考 |
|---|---|
| `session_id` | |
| `transcript_path` | v0.1 では読まない |
| `cwd` | |
| `permission_mode` | |
| `scratchpad_dir` | optional |
| `hook_event_name` | `"PreCompact"` |
| `trigger` | `"manual"` \| `"auto"` |
| `custom_instructions` | `/compact <instructions>` のユーザー入力 |

matcher: `"manual"` / `"auto"`（`"manual|auto"` で両方）

### PostCompact (input, stdin JSON)

```text
hook_event_name:"PostCompact",trigger:t.trigger,compact_summary:t.compactSummary
```

| field | 備考 |
|---|---|
| `session_id`, `transcript_path`, `cwd`, `permission_mode` | 共通 |
| `hook_event_name` | `"PostCompact"` |
| `trigger` | `"manual"` \| `"auto"` |
| `compact_summary` | native compaction が生成した要約 |

matcher: `"manual"` / `"auto"`

### SessionStart (input, stdin JSON)

```text
hook_event_name:"SessionStart",source:t,agent_type:o,model:s,session_title:...
```

`source` の取り得る値: `startup` | `resume` | `clear` | `compact` | **`fork`**

### Hook output (共通)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Text injected into model context"
  }
}
```

公式ドキュメントの記述（そのまま引用）:

- `hookSpecificOutput` — Event-specific output (must include `hookEventName`)
- `additionalContext` — Text injected into model context

## 2. SPEC と現行仕様の差分、および採用判断

### 差分 1 — SessionStart に `fork` source が存在する

- **SPEC**: §7.2 は `startup` / `resume` / `clear` / `compact` の世界観で書かれており `fork` を知らない
- **現行仕様**: `fork` が追加されている
- **採用判断（公式仕様を優先）**:
  - matcher は `"compact"` のみに限定する
  - handler 側でも `source != "compact"` は **必ず no-op**（`fork` を含む）
  - 理由: fork は compaction による欠落ではなく session の分岐であり、
    rehydration の対象ではない。将来 source が増えても allow-list 方式なら安全側に倒れる

### 差分 2 — auto-compaction window はローカルに存在するが公式未文書化

- **SPEC**: §11「If the locally installed Claude Code build exposes a **supported** configurable
  auto-compaction window, document 400k as the initial experimental safety threshold」
  かつ「Do not assume undocumented setting names」「If no supported setting exists in the
  installed build, omit it」
- **ローカルビルドの実測**: 2.1.245 のバイナリには以下が実在する
  - settings キー `autoCompactWindow`（設定キー allow-list 配列に含まれる）
  - 環境変数 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`
  - 関連キー `autoCompactEnabled`
  - バイナリ内の該当メッセージ:
    `set CLAUDE_CODE_AUTO_COMPACT_WINDOW=${i} (or the autoCompactWindow setting)`
    → 値の単位は **トークン数**
- **現行公式ドキュメント**: <https://code.claude.com/docs/en/settings> に
  `autoCompactWindow` / `CLAUDE_CODE_AUTO_COMPACT_WINDOW` の記載は**無い**
- **採用判断（公式仕様を優先）**:
  - `.claude/settings.example.json` には **書かない**
  - SPEC §11 の「400k を初期実験閾値として文書化する」も **v0.1 では行わない**
    （"supported" の条件を満たさないため）
  - [[operations]] には「実在するが未文書化のため v0.1 の推奨構成に含めない」ことと
    上記の検証手順のみを記録する
  - 閾値の探索は v0.2 の benchmark 課題に送る → [[benchmark-plan]]

### 差分 3 — SPEC が列挙していない input フィールドが存在する

- `permission_mode`, `scratchpad_dir`, SessionStart の `model` / `agent_type` / `session_title`,
  PreCompact の `custom_instructions`
- **採用判断**:
  - parser は未知キーを**無視して通す**（forward compatible）
  - SPEC §7.1 の capture 一覧に無いフィールドは **checkpoint に保存しない**。
    特に `custom_instructions` はユーザー入力本文であり、durable memory に本文を
    複製しない原則（SPEC §2.1 / §9）に従って保存対象から外す

## 3. 影響しないと判断した現行挙動

- バイナリには `SKIP_PRECOMPACT_THRESHOLD` / `CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP` が存在するが、
  これは **transcript ファイル読み込みの最適化**（PreCompact 境界以降のみ読む）に関するもので、
  PreCompact **hook の実行**をスキップするものではない。
  v0.1 は transcript を読まないため影響しない。
