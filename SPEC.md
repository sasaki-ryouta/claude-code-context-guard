# Claude Code Context Guard — v0.1.2 Specification

## 1. Purpose

Claude Code の context compaction 前後で、長時間 coding task に必要な高価値な作業状態を project-local filesystem へ外部化し、compaction 後に bounded context として最小限だけ再注入する。v0.1.2 は operational baseline であり native compaction を置き換えない。

Goals: compaction loss軽減、active context縮小、filesystemをsource of truth化、reasoning stateだけdurable化、fail-open、benchmark provenance確保、target repositoryでruntime stateを誤commitしにくくする。

## 2. Design principles

- source code / diff全文 / command output全文 / test log全文は durable memory にしない
- goal / acceptance criteria / phase / decision+rationale / still-relevant rejected approach / unresolved failure / next action / pointersを保持
- `additionalContext` hard cap 9,000 chars
- WORKING_STATE target 6,000 chars、git state cap 2,000 chars
- PreCompactで別LLMを呼ばず transcript bodyを解析しない
- hookはfail-open、doctorだけdiagnostic non-zero可
- project-local、offline、stdlib-only
- target Git repositoryのruntime artifactsはeffective ignore対象であることをdoctorで検証する

## 3. Runtime

Python 3.11+ standard library only。network、database、embedding、vector DB、external LLM、`shell=True`、transcript body parsingは禁止。

## 4. Stable project root

Hook `cwd` は mutable。persistence root resolution orderは valid `CLAUDE_PROJECT_DIR`、lightweightなGit worktree root lookup、current cwd。root fallbackは`git status`を実行しない。CLIはproject dirをinternal payload fieldとしてhandlerへ渡す。checkpoint/eventは`cwd`と`project_root`を記録する。

## 5. Runtime layout

```text
.claude/context-guard/
├── WORKING_STATE.md
└── sessions/<safe-session-id>/
    ├── checkpoint.json
    ├── checkpoint.md
    ├── compact-summary.md
    ├── events.jsonl
    └── compactions/000001/
        ├── checkpoint.json
        ├── checkpoint.md
        └── compact-summary.md
```

Top-level filesはlatest view。per-compaction directoryはimmutable provenance。Git targetではWORKING_STATEとsessions treeをignoreする。

## 6. WORKING_STATE

Sections: Goal、Acceptance criteria、Current phase、Decisions(+Why/Affects)、Current failures(+Evidence/Suspected cause)、Next、Pointers(file/symbol/test/ADR/issue)、Notes。

Rules: <=6,000 chars target、code/log/diff全文禁止、credential禁止、resolved failure削除、superseded decision整理、re-readable raw dataはpointer化。

semantic boundaryでのみ更新: investigation complete、plan stabilized、important decision、root cause、major hypothesis rejection、phase transition、goal change、`/compact`直前。

## 7. Compact Instructions

Preserve goal/criteria/phase/next/decisions+rationale/rejected approaches/unresolved failures/invariants/pointers。Discard verbose tool output、successful output、repeated reads、superseded plans、resolved hypotheses/failures、long source excerpts、cheaply rereadable data。After compactはfilesystem authoritative、re-read before non-trivial edit。

## 8. Hooks

### PreCompact

manual/autoを受け、session/trigger/cwd/project_root/transcript pointer/timestamp/git state/WORKING_STATE snapshot+hash/compaction sequenceを保存。latest checkpointと`compactions/<sequence>/` archiveを書き、event append。LLM/transcript body/full diff/WORKING_STATE mutation/blocking/output injectionは禁止。

### SessionStart(compact)

`source == compact`のみ。current WORKING_STATE + fresh git state + fixed recovery instructionを`hookSpecificOutput.additionalContext`で返す。<=9,000 chars。oversizeはdeterministic truncate + marker + full path。state無しはminimal message。rehydrate eventを記録。

### PostCompact

native `compact_summary`をlatestとlatest compaction archiveへverbatim保存しevent記録。archiveはduplicate PostCompactでrewriteしない。preceding PreCompact無しならlatestのみ、sequence null。summaryは再注入しない。

## 9. Security / privacy

session_id sanitize、path traversal防止、writeは`.claude/context-guard`配下、payload値をcommand実行しない、global settings変更禁止。Transcript/source/logをsecret探索しない一方redaction機能も無い。WORKING_STATE snapshotとnative summaryはverbatim保存されるためsensitive dataを含み得る。Git projectではruntime stateがignoreされ、既trackedでないことをdoctorで検証する。doctorはignore設定を自動変更しない。

## 10. Configuration

`.claude/settings.example.json`: PreCompact `manual|auto` -> `pre-compact`、SessionStart `compact` -> `session-start`、PostCompact `manual|auto` -> `post-compact`。user-global settingsは自動変更しない。別projectでabsolute local `PYTHONPATH`を使う場合は`.claude/settings.local.json`を推奨する。

## 11. Compaction policy

Token thresholdには依存しない。semantic/manual compactionをprimary、native autoをsafety netとする。undocumented threshold settingsはdefault recommendationに入れない。

## 12. Observability

`events.jsonl` event types: pre_compact/post_compact/rehydrate/hook_error。where applicable: timestamp、session_id、compaction_sequence、trigger/source、cwd、project_root、size/hash、branch/HEAD、duration_ms。transcript bodyは禁止。

## 13. CLI / doctor

`python -m context_guard pre-compact|session-start|post-compact|doctor`。Doctorはread-onlyでPython、project root、WORKING_STATE存在/budget、required event+matcher+expected command、importability、git availability、Git runtime ignore/tracked safetyを検査。empty hook arrays、unignored runtime stateはfail。non-Git projectではignore checkはnot applicable。

## 14. Tests / CI

Testsはstdlib unittest。subdirectory cwd、CLAUDE_PROJECT_DIR fallback、lightweight root lookup、multiple compaction archive、hook source allow-list、budget、malformed input、non-git、path traversal、secret-unaware persistence contract、doctor wiring、runtime gitignore safety、runtime purityをcover。CIはubuntu-latest Python 3.11/3.12/3.13でcompileall + unittest。

## 15. Acceptance criteria

CI全matrix pass、subdirectory compactでroot state利用、root resolutionでduplicate git statusを避ける、rehydration<=9k、PreCompact non-blocking、複数compaction provenance保持、doctor miswire/unignored runtime state拒否、non-git fail-open、path traversal防止、stdlib/offline/DB-free、setup/smoke/privacy/retention/uninstall docs完備。

## 16. Non-goals

FTS/BM25、SQLite、embeddings、vector search/database、knowledge graph、event-derived reducer、transcript semantic extraction、automatic LLM handoff、automatic semantic `/compact`、fine-tuning、daemon、cloud、UI、MCP、global installer。

## 17. Roadmap

v0.2 benchmark harness/native baseline/WORKING_STATE ablation/hook ablation/semantic-boundary experiment/threshold experiment(if supported)/task outcome。v0.3 lexical retrieval。v0.4 semantic/hybrid retrieval only if gap exists。v0.5 causal/state graph only if incremental value measurable。

Primary research question: How much of long-running Claude Code performance degradation can be avoided with project-local, training-free context management while keeping active working context small?
