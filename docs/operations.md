---
title: Operations
date: 2026-09-11
tags: [operations, compaction, hooks]
status: operational-baseline
type: reference
---

# Operations (v0.1.1)

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

session 中に `cd src` しても state は通常 `$CLAUDE_PROJECT_DIR/.claude/context-guard` に残る。fallback は Git worktree root、その次に current cwd。checkpoint には `cwd` と `project_root` の両方を記録する。

## 3. doctor

```bash
PYTHONPATH=/path/to/context-guard/src python3 -m context_guard doctor
```

Python、project root、WORKING_STATE、budget、3 hook の event/matcher/command wiring、importability、git status を検査する。空の hook array や typo は healthy とみなさない。

## 4. Telemetry

`events.jsonl` に `pre_compact` / `post_compact` / `rehydrate` / `hook_error` を記録する。可能な event には `compaction_sequence`、`cwd`、`project_root`、size/hash、branch/HEAD、`duration_ms` を含める。

複数 compaction の provenance は `sessions/<id>/compactions/000001/` 以下。

## 5. Troubleshooting

| symptom | check |
|---|---|
| compaction後にstateが戻らない | `doctor`、SessionStart matcher、events |
| WORKING_STATE missing | resolved project root |
| stateが古い | compact前にstateを更新したか |
| hook_error | PYTHONPATH、write permission、project root |
| archive summary無し | PostCompact event |
| sessions増加 | retentionは手動 |

## 6. Auto-compaction threshold

v0.1.1 は特定 threshold を設定しない。Claude Code 2.1.245 binary では `autoCompactWindow` / `CLAUDE_CODE_AUTO_COMPACT_WINDOW` の存在を確認したが compatibility 確認時点で公式 settings docs に無いため default recommendation に含めない。semantic manual compaction + native auto safety net を使う。

## 7. Sensitive data

`.claude/context-guard/` は gitignored だが secret store ではない。`WORKING_STATE` snapshot と native compact summary は verbatim 保存する。含まれた sensitive data も残る。誤って credential を含めた場合は該当 session を削除し、credential を rotate する。

## 8. Retention

v0.1.1 は benchmark provenance のため自動 retention をしない。不要な session は `rm -rf .claude/context-guard/sessions/<session-id>` で削除する。

## 9. Upgrade / uninstall

upgrade後は `doctor` と unittest suite を実行する。uninstall は project-local hook entries と runtime state を削除する。global settings は自動変更しない。
