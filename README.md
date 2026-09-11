# Claude Code Context Guard

Claude Code の context compaction を跨いで**作業状態だけ**を外部化し、compaction 後に
**最小限だけ**注入し直す project-local な hook 実装。

- native compaction を置き換えない。二重要約もしない
- LLM を呼ばない。network も database も使わない
- runtime dependency は **Python 標準ライブラリのみ**
- hook 障害は **fail-open**。compaction を止めない

仕様は [SPEC.md](SPEC.md)、設計根拠は [docs/architecture.md](docs/architecture.md)、
現行 Claude Code で実測した hook schema は [docs/compatibility.md](docs/compatibility.md)。

## 動作確認済み環境

| | |
|---|---|
| Claude Code | 2.1.245 |
| Python | 3.11+ |
| OS | macOS (darwin)。Linux も動作想定 |

## 5 分セットアップ

### 1. リポジトリを置く (30 秒)

対象プロジェクトの中か、隣に clone する。

```bash
git clone <this-repo> claude-code-context-guard
```

このリポジトリ自身を対象プロジェクトとして使う場合は、そのまま次へ進む。

### 2. hook を設定する (2 分)

対象プロジェクトの `.claude/settings.json` に hook を登録する。
雛形をコピーする:

```bash
cp .claude/settings.example.json .claude/settings.json
```

> [!IMPORTANT]
> `~/.claude/settings.json`（ユーザー global）は**触らない**。project-local だけで完結する。

雛形は `$CLAUDE_PROJECT_DIR/src` を `PYTHONPATH` に渡す。
**別のプロジェクトから使う場合**は、3 箇所の `command` を context-guard の実際の位置に書き換える:

```json
"command": "PYTHONPATH=\"/absolute/path/to/claude-code-context-guard/src\" python3 -m context_guard pre-compact"
```

登録される hook は 3 つ:

| event | matcher | 役割 |
|---|---|---|
| `PreCompact` | `manual\|auto` | compaction 直前に working state を checkpoint する |
| `SessionStart` | `compact` | compaction 直後に recovery context を注入する |
| `PostCompact` | `manual\|auto` | native summary を永続化する |

### 3. WORKING_STATE を作る (1 分)

```bash
mkdir -p .claude/context-guard
cp .claude/context-guard/WORKING_STATE.template.md .claude/context-guard/WORKING_STATE.md
```

`WORKING_STATE.md` を埋める。書式とルールは [SPEC.md](SPEC.md) §5、
更新タイミングは root [CLAUDE.md](CLAUDE.md)。**6,000 characters 以内**に保つ。

### 4. CLAUDE.md に Compact Instructions を置く (1 分)

このリポジトリの [CLAUDE.md](CLAUDE.md) の `# Compact Instructions` 節と
`## Working state instructions` 節を、対象プロジェクトの `CLAUDE.md` にコピーする。

### 5. 検証する (30 秒)

```bash
PYTHONPATH=src python3 -m context_guard doctor
```

Claude Code を再起動して設定を読み込ませる。

## 動作確認

### hook を手で叩く

Claude Code を起動せずに 3 つの hook を検証できる。

```bash
# PreCompact: checkpoint が作られる
echo '{"session_id":"smoke-1","cwd":"'"$PWD"'","hook_event_name":"PreCompact","trigger":"manual","transcript_path":"/dev/null"}' \
  | PYTHONPATH=src python3 -m context_guard pre-compact
cat .claude/context-guard/sessions/smoke-1/checkpoint.json
```

```bash
# SessionStart(compact): additionalContext が返る
echo '{"session_id":"smoke-1","cwd":"'"$PWD"'","hook_event_name":"SessionStart","source":"compact"}' \
  | PYTHONPATH=src python3 -m context_guard session-start
```

```bash
# SessionStart(startup): 何も注入しない（出力なし）
echo '{"session_id":"smoke-1","cwd":"'"$PWD"'","hook_event_name":"SessionStart","source":"startup"}' \
  | PYTHONPATH=src python3 -m context_guard session-start
```

```bash
# PostCompact: summary が保存される
echo '{"session_id":"smoke-1","cwd":"'"$PWD"'","hook_event_name":"PostCompact","trigger":"auto","compact_summary":"hello"}' \
  | PYTHONPATH=src python3 -m context_guard post-compact
cat .claude/context-guard/sessions/smoke-1/compact-summary.md
```

```bash
# fail-open: 壊れた入力でも exit 0
echo 'not json' | PYTHONPATH=src python3 -m context_guard pre-compact; echo "exit=$?"
```

### Claude Code 上で確認する

1. 何か作業して `WORKING_STATE.md` を更新する
2. `/compact` を実行する
3. compaction 後の最初の応答に、注入された goal / next action が反映されているか見る
4. `.claude/context-guard/sessions/<session-id>/events.jsonl` に
   `pre_compact` → `post_compact` → `rehydrate` が並んでいるか確認する

## テスト

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

第三者ライブラリは不要。`unittest` のみ。

## 生成されるファイル

```text
.claude/context-guard/
├── WORKING_STATE.md            # あなたが保守する working memory
└── sessions/
    └── <safe-session-id>/
        ├── checkpoint.json     # PreCompact の構造化 checkpoint
        ├── checkpoint.md       # 同じ内容の人間可読版
        ├── compact-summary.md  # PostCompact が保存した native summary
        └── events.jsonl        # append-only の観測ログ
```

`.gitignore` で除外済み。**自動 commit はしない**。

## 保存しないもの

- transcript 本文（`transcript_path` は文字列として記録するだけで、開かない）
- source code 本文 / diff 全文 / command output 全文
- secret / token / password

理由は [docs/architecture.md](docs/architecture.md) §2。

## Uninstall

```bash
# 1. hook 登録を外す（.claude/settings.json の hooks から 3 つのブロックを削除）
#    settings.json 全体が context-guard 専用なら、ファイルごと削除してよい
rm .claude/settings.json

# 2. runtime state を消す
rm -rf .claude/context-guard/sessions .claude/context-guard/WORKING_STATE.md

# 3. 対象プロジェクトの CLAUDE.md から Compact Instructions 節を消す（任意）
```

ユーザー global の `~/.claude/settings.json` は最初から変更していないので、戻す作業はない。

## v0.1 の位置づけ

v0.1 は**測定のための基盤**であり、効果が証明された構成ではない。
native compaction との比較計画は [docs/benchmark-plan.md](docs/benchmark-plan.md)、
段階計画は [docs/roadmap.md](docs/roadmap.md)。
