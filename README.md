# Claude Code Context Guard

Claude Code の context compaction を跨いで、**高価値な作業状態だけ**を project-local に退避し、compaction 後に小さな recovery context として戻す lightweight hook 実装です。

> [!important]
> **導入を検討している方へ。** 自動の state 再注入か、検査可能な compaction checkpoint が、あなたが既に抱えている問題を解決するなら導入してください。
> 正確な `WORKING_STATE.md` の維持は依然としてあなたの仕事です。
> 事前登録した pilot では、**維持された state のみの場合に対する一貫した有用な増分は見つかりませんでした**。
> コーディング成果の改善も実証されていません。
> 維持された state で足りていて checkpoint アーカイブが不要なら、**導入を見送ってください**。
>
> 詳細は [docs/h1-pilot-results.md](docs/h1-pilot-results.md)。

v0.1.2 の設計は意図的に単純です。

- native compaction を置き換えない
- PreCompact で別 LLM を呼ばない
- transcript 本文を解析・複製しない
- code / diff / command log を durable memory にしない
- runtime dependency は Python 3.11+ の標準ライブラリのみ
- hook failure は fail-open。compaction を止めない
- `WORKING_STATE.md` + current git state だけを bounded rehydration する

仕様は [SPEC.md](SPEC.md)、設計は [docs/architecture.md](docs/architecture.md)、Claude Code compatibility は [docs/compatibility.md](docs/compatibility.md)、運用判断は [docs/operations.md](docs/operations.md) を参照してください。実 Claude Code lifecycle の検証手順は [docs/live-smoke.md](docs/live-smoke.md) に固定しています。

## このツールが主張すること / しないこと

| | |
|---|---|
| **する** | compaction 前に決定的な checkpoint を残す。compaction 後に上限付き（9,000 chars 以下）の recovery context を注入する。hook 障害時に compaction を止めない |
| **しない** | working state を**代わりに維持すること**。記録されなかった情報を復元すること。記憶の保全を保証すること。コーディング成果の改善 |

`fail-open` が保証するのは **workflow の継続であって記憶の保全ではありません**。
hook は state を書きません。あなたが `WORKING_STATE.md` に書かなかったことは、compaction 後にも存在しません。

## 検証対象

| 項目 | 状態 |
|---|---|
| Claude Code | 2.1.245 で hook schema + 実 `/compact` lifecycle を確認 |
| Python | 3.11+ |
| macOS | Darwin 25.6.0 arm64 / Python 3.13.2 で live smoke PASS |
| Linux | GitHub Actions で 3.11 / 3.12 / 3.13 を検証 |

Live smoke では `LIVE-SMOKE-GOAL` / `LIVE-SMOKE-DECISION` / `LIVE-SMOKE-NEXT` の3 markerがcompactionを越えてrehydrated contextだけから復元され、`rehydrate.context_chars` は 1058、`hook_error` は0件でした。Claude Code 2.1.245 で観測したhook順序は `PreCompact -> SessionStart(source=compact) -> PostCompact` です。実装はこの順序に依存しません。

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

## まず試す native-first 構成

H1 pilot が直接支持するのは、**Context Guard rehydration hooks を default に昇格させる根拠が得られなかった**という限定的な結論です。Auto Memory、manual `/compact`、native auto-compaction の日常運用上の組み合わせ自体を H1 が検証したわけではありません。

その上で、運用を単純に保つ baseline として次を推奨します。

```text
user-level ~/.claude/CLAUDE.md policy
+ Claude Code Auto Memory enabled
+ checkout-local WORKING_STATE.local.md
+ semantic manual /compact when useful
+ native auto-compaction as a safety net
+ no Context Guard hooks by default
```

copyable な global policy、project opt-in、state ownership、Git ignore、H1 の evidence boundary は [docs/native-first-setup.md](docs/native-first-setup.md) を参照してください。

- global example: [examples/global-CLAUDE.md](examples/global-CLAUDE.md)
- project-local opt-in example: [examples/project-CLAUDE.local.md](examples/project-CLAUDE.local.md)
- working-state schema: [.claude/context-guard/WORKING_STATE.template.md](.claude/context-guard/WORKING_STATE.template.md)

native-first baseline では、`CLAUDE.local.md` と `WORKING_STATE.local.md` を checkout-local として Git から除外します。Context Guard を導入する場合のみ、supported runtime path の `.claude/context-guard/WORKING_STATE.md` に切り替えます。

Auto Memory を無効化する環境変数は benchmark で persistence channel を分離するために使った control です。`--setting-sources project` も user/local settings を制御する isolation の一部でしたが、それだけで全 host surface の除去を保証したわけではありません。benchmark では Auto Memory の個別無効化と observed host surface の検証も併用しています。

## Context Guard hooks を使う場合の5分セットアップ

### 1. Context Guard を配置

```bash
git clone https://github.com/sasaki-ryouta/claude-code-context-guard.git
```

### 2. target project の local state をGitから除外

Context Guard自身の`.gitignore`は別repositoryには効きません。**target project側**の`.gitignore`へ最低限以下を追加してください。

```gitignore
# Claude Code Context Guard local runtime
.claude/context-guard/WORKING_STATE.md
.claude/context-guard/sessions/
```

外部projectからabsolute `PYTHONPATH`でContext Guardを呼ぶ場合は、machine-local設定をcommitしないためこれも推奨します。

```gitignore
.claude/settings.local.json
```

`doctor` はGit projectでruntime stateがeffective ignore対象になっていない場合、unsafeとして失敗します。ignore設定自体は自動変更しません。

### 3. project-local hook を設定

この repository 自身なら:

```bash
cp .claude/settings.example.json .claude/settings.json
```

別 project から使う場合は **`.claude/settings.local.json`** に3つのhookを登録し、`PYTHONPATH`をContext Guardの絶対パスへ変更してください。machine固有absolute pathを共有settingsへ入れないためです。

```json
"command": "PYTHONPATH=\"/absolute/path/to/claude-code-context-guard/src\" python3 -m context_guard pre-compact"
```

`~/.claude/settings.json` は変更しません。

| event | matcher | role |
|---|---|---|
| `PreCompact` | `manual\|auto` | working state checkpoint |
| `SessionStart` | `compact` | bounded rehydration |
| `PostCompact` | `manual\|auto` | native summary persistence |

### 4. WORKING_STATE を作成

```bash
mkdir -p .claude/context-guard
cp /path/to/claude-code-context-guard/.claude/context-guard/WORKING_STATE.template.md \
  .claude/context-guard/WORKING_STATE.md
```

`WORKING_STATE.md` は 6,000 characters 以下を目安にします。goal、acceptance criteria、current phase、decision/rationale、未解決 failure、next action、file/symbol/test/ADR pointer を保持します。

### 5. CLAUDE.md を導入して doctor

Context Guard repository の `CLAUDE.md` にある `Working state instructions`、`When to recommend /compact`、`Compact Instructions` をtarget projectの`CLAUDE.md`へコピーします。

```bash
PYTHONPATH=/absolute/path/to/claude-code-context-guard/src python3 -m context_guard doctor
```

この repository 自身なら `PYTHONPATH=src python3 -m context_guard doctor`。

`doctor` は Python、resolved project root、WORKING_STATE の存在/budget、3 hook の event/matcher/command wiring、importability、git status、runtime artifactのGit ignore safetyを検査し、設定は変更しません。

## 日常運用

基本は **semantic compaction** です。investigation完了、plan確定、root cause判明、major implementation完了、verification移行などの境界で、まず working state を更新してから `/compact` を実行します。auto-compaction は safety net として扱います。このプロジェクトは特定の numeric threshold を最適値として主張しません。

Auto Memory と working state は同じ情報を重複保持させず、前者を durable な cross-session learning、後者を volatile な current-task handoff として分離するのが baseline です。

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

top-level checkpoint/summary は最新 view、`compactions/<sequence>/` は benchmark と事後検証用の履歴です。target Git projectでは `doctor` がこれらのignore状態を検証します。自動commitはしません。

## Privacy / sensitive data

Context Guard 自身は transcript 本文を開かず、secret/token/password を探索・抽出しません。ただし、**secret redaction 機能もありません**。

`WORKING_STATE.md` snapshot と Claude Code の native `compact_summary` はローカルへ verbatim 保存されるため、その中に機密情報が含まれていれば runtime artifact に残ります。credential を `WORKING_STATE.md` に書かず、`.claude/context-guard/` は local sensitive runtime data として扱ってください。Git projectでは必ず`doctor`の`Runtime gitignore: ok`を確認してください。

## テスト

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

CI でも同じ suite を Python 3.11 / 3.12 / 3.13 で実行します。

## Smoke test

fixture/CLI smoke と real lifecycle smoke を区別します。unit/CI は hook handler と persistence contract を検証し、実際の Claude Code が hook を発火する境界は [docs/live-smoke.md](docs/live-smoke.md) で確認します。

## Uninstall

1. target project の `.claude/settings.json` / `.claude/settings.local.json` から3 hookを削除
2. runtime state が不要なら `.claude/context-guard/WORKING_STATE.md` と `sessions/` を削除
3. `CLAUDE.md` から Context Guard 用 instruction を削除
4. 不要ならtarget projectへ追加した`.gitignore` rulesを削除

Context Guard は global settings を自動変更しません。

## 現在の位置づけ

v0.1.2 は **live-validated operational baseline** です。hook lifecycle と安全性は確認済みですが、H1 pilot は maintained state のみの場合に対する一貫した有用な rehydration increment を示しませんでした。そのため hook は default recommendation ではなく、automatic reinsertion や inspectable checkpoint が具体的に必要なproject向けの optional mechanism として扱います。

研究ロードマップは [docs/roadmap.md](docs/roadmap.md) のとおり closed です。FTS/BM25、embeddings、vector DB、knowledge graph、automatic LLM handoff を結果救済のために追加しません。
