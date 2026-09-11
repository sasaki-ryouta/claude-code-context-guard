---
title: Benchmark plan
date: 2026-09-11
tags: [benchmark, evaluation, compaction]
status: draft
type: reference
---

# Benchmark plan (v0.2 に向けて)

v0.1 は**測定のための基盤**であり、効果が証明された構成ではない。
このドキュメントは「native Claude Code compaction と比べて context-guard に価値があるか」を
測るための計画である。設計根拠は [[architecture]]、運用は [[operations]]。

> [!warning]
> v0.1 の時点で効果の主張をしてはならない。まだ何も測っていない。

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
| **A. baseline** | なし | なし | native auto のみ |
| **B. state only** | あり（Claude が保守） | なし | native auto のみ |
| **C. full** | あり | 有効 | native auto + semantic manual |
| **D. hooks only** | なし | 有効 | native auto |

- **B vs C** が hook（rehydration）の寄与を分離する
- **A vs B** が「WORKING_STATE を書くこと自体」の寄与を分離する（ablation）
- **D** は state が無いときの hook の無害性の確認（劣化させていないこと）

## 3. task suite

再現性のため、**同じ repository の同じ初期 commit** から開始する固定 task を使う。

task は「compaction を確実に1回以上跨ぐ長さ」であることが条件。候補の型:

1. **multi-file refactor** — 呼び出し元の追跡が必要。決定の rationale が効く
2. **bug の根因調査 → 修正** — 棄却した仮説の記憶が効く
3. **仕様からの新機能実装** — acceptance criteria の保持が効く
4. **failing test の連続修正** — unresolved failure の保持が効く

各 task について: 初期 commit、prompt、成功判定スクリプト（テスト or 検証コマンド）を固定する。

## 4. 測る指標

### 4.1 compaction survival（H1）— 主指標

compaction 直後の最初の応答に対して、次の項目が保持されているかを採点する。

| 項目 | 採点 |
|---|---|
| current goal | 保持 / 劣化 / 消失 |
| acceptance criteria | 同 |
| current phase | 同 |
| next action | 同 |
| unresolved failure | 同 |
| 主要 decision の rationale | 同 |
| 棄却した approach | 同 |

採点は rubric ベースで、**採点者を条件名から盲検化**する（arm 名を伏せた transcript 断片で採点）。

### 4.2 context size（H2）

- compaction 直後の active context のトークン数
- 注入した `additionalContext` の実測 chars（`events.jsonl` の `rehydrate` から取得可能にする）

### 4.3 task outcome（H3）

- 成功判定スクリプトの pass/fail
- compaction 後に**同じファイルを読み直した回数**（stale memory による手戻りの代理指標）
- compaction 後に**既に棄却した approach を再試行した回数**
- 総 turn 数 / 総トークン数

### 4.4 コスト

- hook の実行時間（`events.jsonl` に記録できるようにする）
- 注入トークンの総量

## 5. 手続き

1. arm ごとに `.claude/settings.json` を切り替える（`settings.example.json` の有無で表現できる）
2. 同一 task を **n ≥ 5** 回反復する（LLM の非決定性を吸収する。n は pilot で決める）
3. 各 run の `.claude/context-guard/sessions/<id>/events.jsonl` と transcript を保存する
4. compaction の発生位置を `pre_compact` / `post_compact` イベントで特定する
5. compaction 直後の応答を切り出して盲検採点する

## 6. threshold sweep（H4）

[[compatibility]] の差分 2 のとおり、`autoCompactWindow` は 2.1.245 のバイナリに実在するが
公式未文書化である。v0.2 で sweep する場合:

- 公式ドキュメントに記載されたことを**再確認してから**使う
- 記載が無いままなら、`/compact` の手動タイミングを変える（turn 数・phase 境界）ことで
  実効的な window を近似する
- sweep する値は pilot で決める。v0.1 は特定の閾値を推奨しない

## 7. 交絡因子と対処

| 交絡 | 対処 |
|---|---|
| model の更新 | 全 arm を同一日・同一 model id で回し、model id を記録する |
| task の学習効果（同じ repo を繰り返す） | 初期 commit を固定し、worktree を毎回破棄する |
| WORKING_STATE の品質差 | 更新境界を CLAUDE.md で固定し、手書きで補正しない |
| 採点者バイアス | 盲検採点 + rubric の事前固定 |
| compaction 回数の差 | 「compaction 1 回あたり」で正規化する |

## 8. 撤退条件

次のいずれかなら、**v0.3 以降の retrieval 機構には進まない**。

- H1 で B と C の差が n ≥ 5 で有意でない → rehydration は効いていない。
  hook ではなく WORKING_STATE の運用が効いている（なら hook を捨てる）
- H3 で C が A を改善しない → 注入コストを払う価値がない
- H2 で注入が context を実質的に膨らませている → budget 設計の見直しが先

SPEC §18 のとおり、**v0.1 以降の全機能は測定可能な改善を示してから**推奨構成に入る。
