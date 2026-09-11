# Claude Code Context Guard

Claude Code の context compaction を跨いで、**高価値な作業状態だけ**を project-local に退避し、compaction 後に小さな recovery context として戻す lightweight hook 実装です。

v0.1.1 の設計は意図的に単純です。

- native compaction を置き換えない
- PreCompact で別 LLM を呼ばない
- transcript 本文を解析・複製しない
- code / diff / command log を durable memory にしない
- runtime dependency は Python 3.11+ の標準ライブラリのみ
- hook failure は fail-open。compaction を止めない
- `WORKING_STATE.md` + current git state だけを bounded rehydration する

仕様は [SPEC.md](SPEC.md)、設計は [docs/architecture.md](docs/architecture.md)、Claude Code compatibility は [docs/compatibility.md](docs/compatibility.md)、運用判断は [docs/operations.md](docs/operations.md) を参照してください。実 Claude Code lifecycle の検証手順は [docs/live-smoke.md](docs/live-smoke.md) に固定しています。

## 検証対象

| 項目 | 状態 |
|---|---|
| Claude Code | 2.1.245 で hook schema を確認 |
| Python | 3.11+ |
| macOS | ローカル lifecycle smoke を `docs/live-smoke.md` で実施 |
| Linux | GitHub Actions で 3.11 / 3.12 / 3.13 を検証 |

## 仕組み

```text
WORKING_STATE.md
      |
      | semantic boundary で Claude が更新
      v
PreCompact -> checkpoint + per-compaction archive
      |
native Claude Code compact
      |
PostCompact -> native summary persistence
      |
SessionStart(source=compact) -> <= 9,000 chars rehydrate
```

`cwd` が session 中に `cd` で変わっても、hook command が継承する `CLAUDE_PROJECT_DIR` を stable project root として優先します。直接呼び出し時は Git root、それも無ければ current `cwd` にフォールバックします。

## 5分セットアップ

### 1. Context Guard を配置

```bash
git clone https://github.com/sasaki-ryouta/claude-code-context-guard.git
```

### 2. project-local hook を設定

この repository 自身なら:

```bash
cp .claude/settings.example.json .claude/settings.json
```

別 project から使う場合は、対象 project の `.claude/settings.json` に3つの hookを登録し、`PYTHONPATH` だけ Context Guard の絶対パスへ変更してください。

```json
"command": "PYTHONPATH=\"/absolute/path/to/claude-code-context-guard/src\" python3 -m context_guard pre-compact"
```

`~/.claude/settings.json` は変更しません。

| event | matcher | role |
|---|---|---|
| `PreCompact` | `manual\|auto` | working state checkpoint |
| `SessionStart` | `compact` | bounded rehydration |
| `PostCompact` | `manual\|auto` | native summary persistence |

### 3. WORKING_STATE を作成

```bash
mkdir -p .claude/context-guard
cp .claude/context-guard/WORKING_STATE.template.md .claude/context-guard/WORKING_STATE.md
```

`WORKING_STATE.md` は 6,000 characters 以下を目安にします。goal、acceptance criteria、current phase、decision/rationale、未解決 failure、next action、file/symbol/test/ADR pointer を保持します。

### 4. CLAUDE.md を導入

この repository の `CLAUDE.md` にある `Working state instructions`、`When to recommend /compact`、`Compact Instructions` を対象 project の `CLAUDE.md` へコピーします。

### 5. doctor

```bash
PYTHONPATH=/absolute/path/to/claude-code-context-guard/src python3 -m context_guard doctor
```

この repository 自身なら `PYTHONPATH=src python3 -m context_guard doctor`。

`doctor` は Python、resolved project root、WORKING_STATE の存在/budget、3 hook の event/matcher/command wiring、importability、git status を検査し、設定は変更しません。

## 日常運用

基本は **semantic compaction** です。investigation完了、plan確定、root cause判明、major implementation完了、verification移行などの境界で、まず `WORKING_STATE.md` を更新してから `/compact` を実行します。auto-compaction は safety net として扱います。v0.1.1 は特定の token threshold に依存しません。

Claude Code または Context Guard を更新した後は、[live smoke runbook](docs/live-smoke.md) を1回通してから日常利用へ戻します。

## runtime artifacts

```text
.claude/context-guard/
├── WORKING_STATE.md
└── sessions/
    └── <safe-session-id>/
        ├── checkpoint.json
        ├── checkpoint.md
        ├── compact-summary.md
        ├── events.jsonl
        └── compactions/
            ├── 000001/
            │   ├── checkpoint.json
            │   ├── checkpoint.md
            │   └── compact-summary.md
            └── 000002/
                └── ...
```

top-level checkpoint/summary は最新 view、`compactions/<sequence>/` は benchmark と事後検証用の履歴です。すべて `.gitignore` 対象で、自動 commit しません。

## Privacy / sensitive data

Context Guard 自身は transcript 本文を開かず、secret/token/password を探索・抽出しません。ただし、**secret redaction 機能もありません**。

`WORKING_STATE.md` snapshot と Claude Code の native `compact_summary` はローカルへ verbatim 保存されるため、その中に機密情報が含まれていれば runtime artifact に残ります。credential を `WORKING_STATE.md` に書かず、`.claude/context-guard/` は local sensitive runtime data として扱ってください。

## テスト

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CI でも同じ suite を Python 3.11 / 3.12 / 3.13 で実行します。

## Smoke test

fixture/CLI smoke と real lifecycle smoke を区別します。unit/CI は hook handler と persistence contract を検証し、実際の Claude Code が hook を発火する境界は [docs/live-smoke.md](docs/live-smoke.md) で確認します。

## Uninstall

1. 対象 project の `.claude/settings.json` / `.claude/settings.local.json` から3 hookを削除
2. runtime state が不要なら `.claude/context-guard/WORKING_STATE.md` と `sessions/` を削除
3. `CLAUDE.md` から Context Guard 用 instruction を削除

Context Guard は global settings を自動変更しません。

## 現在の位置づけ

v0.1.1 は **operational baseline** です。外部 memory の有効性を証明したものではありません。次は [docs/benchmark-plan.md](docs/benchmark-plan.md) に従って native compaction、state-only、full guard を ablation し、改善が測定できた機能だけを追加します。

FTS/BM25、embeddings、vector DB、knowledge graph、automatic LLM handoff はまだ default architecture に入れません。
