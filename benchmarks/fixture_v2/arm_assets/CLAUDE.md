# RouteForge

This project keeps `.claude/context-guard/WORKING_STATE.md` as explicit working memory.

## Working state instructions

Update `.claude/context-guard/WORKING_STATE.md` at these semantic boundaries. Do not update it every turn.

- an investigation phase completes
- a plan stabilizes
- an important decision is settled
- work moves into an implementation phase
- a root cause is identified
- a major hypothesis is rejected
- work moves into a verification phase
- the task goal changes

Follow the headings already present in the file. Constraints:

- keep it under 6,000 characters
- do not paste full source code, full command output, or full diffs
- do not duplicate information that is cheap to reread from the filesystem
- delete resolved failures; delete superseded decisions or mark them `(superseded)`
- record distinctive identifiers exactly as they appear in the source documents
- never write secrets, tokens, or passwords

# Compact Instructions

## Preserve

- current goal
- acceptance criteria
- current phase
- unresolved next step
- architectural and implementation decisions
- rationale for non-obvious decisions
- relevant rejected approaches
- modified / relevant file pointers
- unresolved failing tests and errors
- important invariants and constraints

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
