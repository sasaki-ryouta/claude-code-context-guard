---
title: Operations
date: 2026-09-11
tags: [operations, compaction, hooks]
status: operational-baseline
type: reference
---

# Operations (v0.1.2)

日常運用の目的は active working set を高 signal に保つこと。

## 1. Daily loop

1. 作業する
2. semantic boundary に到達する
3. `WORKING_STATE.md` を現在状態へ更新
4. その直後に `/compact`
5. rehydrated state を pointer として relevant files を再読
6. 次 phase を開始

重要なのは state 更新 **before** `/compact`。

## 2. Stable project root

session 中に `cd src` しても state は通常 `$CLAUDE_PROJECT_DIR/.claude/context-guard` に残る。fallback は lightweightな`git rev-parse --show-toplevel`、その次にcurrent cwd。root resolutionでは`git status`を実行せず、full git telemetryが必要な箇所だけで収集する。checkpointには`cwd`と`project_root`を両方記録する。

## 3. Target-project Git safety

別repositoryで使う場合、このrepositoryの`.gitignore`は効かない。target側で最低限以下をignoreする。

```gitignore
.claude/context-guard/WORKING_STATE.md
.claude/context-guard/sessions/
```

absolute `PYTHONPATH`を含むmachine-local hook wiringは`.claude/settings.local.json`に置き、このfileもtarget側でignoreすることを推奨する。

`doctor`はGit projectに対してeffective `git check-ignore`を検査し、runtime pathsがignoreされていない、またはruntime artifactsが既にtrackedの場合はfailする。自動修正はしない。

## 4. doctor

```bash
PYTHONPATH=/path/to/context-guard/src python3 -m context_guard doctor
```

Python、project root、WORKING_STATE、budget、3 hookのevent/matcher/command wiring、importability、git status、runtime Git safetyを検査する。空のhook arrayやtypoはhealthyとみなさない。

## 5. Telemetry

`events.jsonl` に `pre_compact` / `post_compact` / `rehydrate` / `hook_error` を記録する。可能なeventには`compaction_sequence`、`cwd`、`project_root`、size/hash、branch/HEAD、`duration_ms`を含める。

複数compactionのprovenanceは`sessions/<id>/compactions/000001/`以下。

## 6. Troubleshooting

| symptom | check |
|---|---|
| compaction後にstateが戻らない | `doctor`、SessionStart matcher、events |
| WORKING_STATE missing | resolved project root |
| `Runtime gitignore: unsafe` | target `.gitignore` と既tracked runtime files |
| stateが古い | compact前にstateを更新したか |
| hook_error | PYTHONPATH、write permission、project root |
| archive summary無し | PostCompact event |
| sessions増加 | retentionは手動 |

既にruntime stateをGitへadd/commitしてしまった場合、ignore ruleだけではtracked状態は解除されない。内容を確認し、必要に応じてGit index/historyから除去し、sensitive credentialが含まれていた場合はrotateする。

## 7. Auto-compaction threshold

v0.1.2 は特定 threshold を設定しない。Claude Code 2.1.245 binaryでは`autoCompactWindow` / `CLAUDE_CODE_AUTO_COMPACT_WINDOW`の存在を確認したがcompatibility確認時点で公式settings docsに無いためdefault recommendationに含めない。semantic manual compaction + native auto safety netを使う。

## 8. Sensitive data

`.claude/context-guard/` はsecret storeではない。`WORKING_STATE` snapshotとnative compact summaryはverbatim保存する。含まれたsensitive dataも残る。誤ってcredentialを含めた場合は該当sessionを削除し、credentialをrotateする。

## 9. Retention

v0.1.2 はbenchmark provenanceのため自動retentionをしない。不要なsessionは`rm -rf .claude/context-guard/sessions/<session-id>`で削除する。

## 10. Live validation

Claude CodeまたはContext Guard更新後は`docs/live-smoke.md`を実行し、実際の`/compact` lifecycleでrehydrationとarchiveを確認する。

## 11. Upgrade / uninstall

upgrade後は`doctor`、unittest suite、live smokeの順で確認する。uninstallはproject-local hook entriesとruntime stateを削除する。global settingsは自動変更しない。
