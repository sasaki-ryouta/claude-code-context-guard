---
title: Operations
date: 2026-09-11
tags: [operations, compaction, hooks]
status: draft
type: reference
---

# Operations

インストール手順は `README.md`。ここでは**運用中の判断**を扱う。
hook schema の実測結果は [[compatibility]]、設計根拠は [[architecture]]。

## 1. 日常の運用ループ

1. 作業する
2. semantic boundary に達したら `.claude/context-guard/WORKING_STATE.md` を更新する
   （境界の一覧は root `CLAUDE.md`）
3. WORKING_STATE を更新した**直後**に手動 `/compact` を推奨・実行する
4. compaction 後、SessionStart(compact) hook が recovery context を注入する
5. 注入された state を**信用しすぎない**。関連ファイルは読み直す

> [!important]
> 順序が逆になると価値が消える。WORKING_STATE を更新する前に compact すると、
> 保存されるのは古い state であり、rehydration はその古い state を復元する。

## 2. インストールの健全性確認

```bash
PYTHONPATH=src python3 -m context_guard doctor
```

`doctor` は設定を**変更しない**。非 0 終了は次のいずれかを意味する:

- WORKING_STATE が 6,000 characters の budget を超えている
- hook 設定が見つからない
- Python version が 3.11 未満
- git status が取得できない（非 git プロジェクトでは警告であって致命ではない）

## 3. 観測データの読み方

```bash
cat .claude/context-guard/sessions/<session-id>/events.jsonl | python3 -m json.tool --json-lines
```

イベント種別は `pre_compact` / `post_compact` / `rehydrate` / `hook_error`。

- `hook_error` が出ていても compaction は成功している（fail-open のため）。
  ただし **checkpoint が欠けている**ので、頻発するなら原因を潰す
- `pre_compact` の `working_state.sha256` が連続して同一なら、
  **WORKING_STATE を更新せずに compact している**。運用ループが守られていない信号
- `post_compact` の `summary_chars` は native compaction の出力規模の目安

## 4. auto-compaction window について

> [!warning]
> v0.1 は auto-compaction の閾値を**設定しない**し、特定の閾値に依存しない。

SPEC §11 は「ローカルビルドが *supported* な設定を露出しているなら 400k を初期実験閾値として
文書化する」と定めている。Claude Code **2.1.245** で実測した結果:

- バイナリには設定キー `autoCompactWindow`、環境変数 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`、
  および `autoCompactEnabled` が**実在する**（値の単位はトークン数）
- しかし現行公式ドキュメント <https://code.claude.com/docs/en/settings> には
  **いずれも記載がない**

したがって "supported" の条件を満たさないと判断し、v0.1 では:

- `.claude/settings.example.json` に書かない
- 400k という具体的な閾値も推奨しない

詳細な判断根拠は [[compatibility]] の「差分 2」。閾値の探索は [[benchmark-plan]] の v0.2 課題。

代わりに採るべき運用方針は **semantic boundary での手動 compaction**であり、
auto-compaction は safety net として既定のまま使う。

## 5. 想定される故障と対処

| 症状 | 原因 | 対処 |
|---|---|---|
| compaction 後に何も注入されない | SessionStart matcher が `compact` でない | `.claude/settings.json` を `settings.example.json` と比較する |
| 注入された state が古い | compact 前に WORKING_STATE を更新していない | 運用ループ (§1) を守る |
| `events.jsonl` に `hook_error` が並ぶ | `PYTHONPATH` かパスの誤り | `doctor` を実行する |
| checkpoint が別ディレクトリに散る | session_id ごとにディレクトリが分かれる正常挙動 | `sessions/` 配下を session_id で辿る |
| session ディレクトリが増え続ける | v0.1 に retention 機構はない | 手で削除する（v0.2 課題） |

## 6. Uninstall

`README.md` の uninstall 手順を参照。`.claude/context-guard/` を削除すれば副作用は残らない。
ユーザー global の `~/.claude/settings.json` は最初から触っていない。
