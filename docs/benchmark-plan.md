---
title: Benchmark plan
date: 2026-09-12
tags: [benchmark, evaluation, compaction]
status: draft
type: reference
---

# Benchmark plan (v0.2 に向けて)

v0.1 は**測定のための基盤**であり、効果が証明された構成ではない。
このドキュメントは「native Claude Code compaction と比べて context-guard に価値があるか」を
測るための計画である。設計根拠は [[architecture]]、運用は [[operations]]。

> [!warning]
> v0.1 の時点で効果の主張をしてはならない。lifecycle correctness は実機確認済みだが、efficacy はまだ測っていない。

> [!note]
> 2026-09-12 の live smoke 実測から、B vs C の fixture validity と exact-marker scoring を追加した。
> live smoke 自体は短く（WORKING_STATE 535 chars、compaction 前会話 1 turn）、benchmark difficulty の証拠には使わない。

## 1. 答えるべき問い

主問（SPEC §19）:

> long-running Claude Code session の性能劣化のうち、どれだけを
> project-local で training-free な context 管理で回避できるか。
> ただし active working context は小さく保ったまま。

v0.2 で答える下位問:

1. **H1 (survival)**: compaction を越えて goal / decisions / next action が保持される率は、
   native compaction 単独より context-guard 有りの方が高いか
2. **H2 (context size)**: compaction 直後の active context は小さく保たれるか
   （9,000 chars の注入というコストを払う価値があるか）
3. **H3 (task outcome)**: compaction を跨ぐ task の完遂率・手戻り回数は改善するか
4. **H4 (threshold)**: auto-compaction window（[[compatibility]] 差分 2）の値は結果に影響するか

## 2. 比較する条件（arm）

| arm | WORKING_STATE | hooks | compaction |
|---|---|---|---|
| **A. baseline** | なし | なし | native auto / benchmark で固定した manual boundary |
| **B. state only** | あり（Claude が保守） | なし | native auto / benchmark で固定した manual boundary |
| **C. full** | あり | 有効 | native auto + benchmark で固定した semantic manual boundary |
| **D. hooks only** | なし | 有効 | native auto / benchmark で固定した manual boundary |

- **B vs C** が hook（rehydration）の寄与を分離する
- **A vs B** が「WORKING_STATE を書くこと自体」の寄与を分離する（ablation）
- **D** は state が無いときの hook の無害性の確認（劣化させていないこと）

### 2.1 B vs C を測れる fixture の妥当性条件

B と C の差を測る task では、`WORKING_STATE.md` を読んだ直後に compact してはいけない。
それでは native summary に state がそのまま残りやすく、rehydration の増分価値を測れない。

fixture は事前に次を満たすこと:

- high-value state を **early phase** で発見・記録する
- その state を最後に読んでから compaction までに **少なくとも 12 substantive turns** を置く
- compaction 前の **直近 8 turns では survival marker を再掲しない**
- intervening work は単なる無意味な padding ではなく、task に必要な investigation / implementation / verification とする
- compact boundary は arm の結果を見て動かさず、fixture spec に事前固定する

この条件は「B を失敗させるため」の tuning ではない。native summary が high-value state を保持できる十分な距離・干渉がある状況を作り、B vs C が飽和した trivial task になることを防ぐための validity gate である。

live smoke の短い state / 1-turn 会話 / 3-of-3 survival は lifecycle correctness の証拠であり、benchmark difficulty の証拠としては扱わない。

## 3. task suite

再現性のため、**同じ repository の同じ初期 commit** から開始する固定 task を使う。

task は「compaction を確実に1回以上跨ぐ長さ」であることが条件。候補の型:

1. **multi-file refactor** — 呼び出し元の追跡が必要。決定の rationale が効く
2. **bug の根因調査 → 修正** — 棄却した仮説の記憶が効く
3. **仕様からの新機能実装** — acceptance criteria の保持が効く
4. **failing test の連続修正** — unresolved failure の保持が効く

各 task について: 初期 commit、prompt、成功判定スクリプト（テスト or 検証コマンド）、manual compact boundary を固定する。

## 4. 測る指標

### 4.1 compaction survival（H1）— 主指標

survival はまず **machine-verifiable exact marker** で測る。fixture ごとに衝突しない一意 token を high-value state に埋め込む。

例:

```text
CGV1-GOAL-7F3A
CGV1-CRITERION-B8D2
CGV1-DECISION-2C91
CGV1-FAILURE-6E44
CGV1-NEXT-4D88
CGV1-REJECTED-91AF
```

compaction 直後、tool access を禁止した probe で該当 state を回答させ、response text に exact token が含まれるかを機械判定する。

| 項目 | primary score |
|---|---|
| current goal | marker present / absent |
| acceptance criterion | marker present / absent |
| next action | marker present / absent |
| unresolved failure | marker present / absent |
| decision rationale | marker present / absent |
| rejected approach | marker present / absent |

**binary survival の primary score に LLM-as-judge は使わない。**
意味は残っているが wording が変わった、矛盾した、部分的に劣化した、などの secondary analysis のみ rubric + arm-blinded human/LLM scoring を使う。

### 4.2 context size（H2）

- compaction 直後の active context のトークン数（取得可能な場合）
- 注入した `additionalContext` の実測 chars（`events.jsonl` の `rehydrate`）

### 4.3 task outcome（H3）

- 成功判定スクリプトの pass/fail
- hidden acceptance tests の pass/fail
- compaction 後に**同じファイルを読み直した回数**（手戻りの代理指標。取得可能な場合）
- compaction 後に**既に棄却した approach を再試行した回数**
- 総 turn 数 / 総トークン数（取得可能な場合）
- wall time

### 4.4 コスト

- hook の実行時間（取得可能な場合）
- 注入 context chars / tokens
- compaction 回数

## 5. 手続き

1. arm ごとに project-local config を切り替える
2. 同一 task をまず小規模 pilot で回し、instrumentation と fixture validity を検証する
3. final sample count は pilot 後に固定する。`n >= 5` は最低線であり、事前に根拠を記録する
4. 各 run の Context Guard events と必要最小限の benchmark provenance を保存する
5. transcript を保存する場合は benchmark 専用 fixture のみとし、実 project transcript は収集しない
6. fixed semantic boundary で `/compact` を発火する
7. compaction 直後に tools disabled の exact-marker probe を実行する
8. marker score は script で自動採点し、secondary rubric を使う場合だけ arm identity を伏せる

## 6. threshold sweep（H4）

[[compatibility]] の差分 2 のとおり、`autoCompactWindow` は 2.1.245 のバイナリに実在するが
公式未文書化である。v0.2 で sweep する場合:

- 公式ドキュメントに記載されたことを**再確認してから**使う
- 記載が無いままなら、`/compact` の手動タイミングを変えることで実効的な window を近似する
- sweep する値は baseline harness が安定した後に別実験として決める
- v0.2 baseline の arm comparison と threshold sweep を同時に変えない

## 7. 交絡因子と対処

| 交絡 | 対処 |
|---|---|
| model の更新 | 全 arm を同一 model id / Claude Code version で回し、実値を記録する |
| task の学習効果 | 初期 commit を固定し、isolated worktree/copy を毎回破棄する |
| WORKING_STATE の品質差 | 更新境界を CLAUDE.md で固定し、run 中に人手補正しない |
| marker の再提示 | compact 前の直近 8 turns では marker を再掲しない |
| compact distance | state 最終参照から compact まで最低 12 substantive turns を固定する |
| 採点者バイアス | exact marker primary score + secondary のみ盲検 rubric |
| compaction 回数の差 | 「compaction 1 回あたり」で正規化し、baseline experiment は fixed boundary を優先する |
| lifecycle order | `PreCompact -> SessionStart -> PostCompact` を仮定せず、event type と sequence で関連付ける |

## 8. 撤退条件

撤退条件は **valid fixture / sufficient sample** でのみ適用する。
trivial fixture（state と compact が近すぎる、marker が直前に再掲される）で B=C になったことを rehydration 無効の根拠にしてはならない。

次のいずれかなら、**v0.3 以降の retrieval 機構には進まない**。

- validity gate を満たした H1 で B と C の差が、事前に固定した sample / analysis で実質的に無い
- H3 で C が A を改善しない、または改善幅が operational cost に見合わない
- H2 で注入が context を実質的に膨らませている → budget 設計の見直しが先

SPEC §18 のとおり、**v0.1 以降の全機能は測定可能な改善を示してから**推奨構成に入る。
