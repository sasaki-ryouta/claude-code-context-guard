# Claude Code Context Guard

このリポジトリは `.claude/context-guard/WORKING_STATE.md` を **明示的な working memory** として使う。
`SPEC.md` が source of truth。仕様と実装が矛盾したら `SPEC.md` を優先し、差分は `docs/compatibility.md` に記録する。

## Working state instructions

`.claude/context-guard/WORKING_STATE.md` を次の **semantic boundary** で更新する。毎 turn 更新しない。

- investigation が完了したとき
- plan が確定したとき
- 重要な decision が確定したとき
- implementation phase に移行したとき
- root cause が判明したとき
- 主要な hypothesis を棄却したとき
- verification phase に移行したとき
- task の goal が変わったとき
- `/compact` をユーザーに推奨する直前

書式は `.claude/context-guard/WORKING_STATE.template.md` に従う。制約:

- **6,000 characters 以内**に保つ（超えると rehydration 時に決定的に切り捨てられる）
- source code 全文・command output 全文・diff 全文を書かない
- filesystem から再取得できる情報を複製しない
- resolved failure は削除する。superseded decision は削除するか `(superseded)` と明示する
- secret / token / password を書かない

## When to recommend /compact

次の状況では、**まず WORKING_STATE.md を更新してから** ユーザーに手動 `/compact` を推奨する。
自分で自動的に compaction を起動しない。

- 大きな investigation phase が完了した
- plan が安定した
- 大きな implementation 単位が完了した
- debugging が収束し verification に入る
- 古くなった tool output が大量に蓄積した

token 閾値による auto-compaction は **safety net** であり、意味的な境界ではない。

# Compact Instructions

## Preserve

- current user goal
- acceptance criteria
- current phase
- unresolved next step
- architectural and implementation decisions
- rationale for non-obvious decisions
- relevant rejected approaches
- modified / relevant file pointers
- unresolved failing tests and errors
- important invariants and constraints
- ADR / issue / test / symbol pointers

## Discard or aggressively compress

- verbose tool output
- successful command output
- repeated file reads
- superseded plans
- resolved hypotheses
- resolved failures
- long source excerpts
- anything cheaply re-readable from the filesystem

## After compaction

- treat the current filesystem as authoritative
- do not trust remembered source snapshots over the current files
- reread relevant files before making non-trivial edits
