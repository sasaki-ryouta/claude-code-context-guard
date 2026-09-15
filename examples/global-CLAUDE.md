# Working-state policy

For non-trivial tasks, maintain a concise project-local working state when the project opts into one.

Update the working state at semantic boundaries, not every turn:

- investigation completed;
- plan stabilized;
- an important decision was made;
- root cause was identified;
- a major hypothesis was rejected;
- a major implementation unit completed;
- verification started;
- the task goal changed;
- immediately before recommending or running a deliberate `/compact`.

Keep only high-value durable state:

- current goal;
- acceptance criteria;
- current phase;
- important decisions and rationale;
- unresolved failures and relevant evidence;
- the next concrete action;
- relevant file, symbol, test, ADR, and issue pointers.

Do not store:

- source-code dumps;
- full diffs;
- full command or tool output;
- repeated file contents;
- resolved failures or superseded plans;
- information cheaply reread from the filesystem;
- secrets, tokens, passwords, or credentials.

Treat the filesystem as authoritative. After compaction, reread the files needed for the next non-trivial edit rather than trusting remembered source snapshots.

# Compaction policy

Use native auto-compaction as a safety net. Prefer deliberate compaction at a semantic boundary when accumulated context is mostly disposable.

Before `/compact`:

1. bring the project-local working state up to date;
2. preserve the current goal, acceptance criteria, phase, next action, important decisions and rationale, unresolved failures, and relevant pointers;
3. aggressively compress or discard verbose tool output, successful command output, repeated reads, resolved hypotheses, superseded plans, and long source excerpts.

After `/compact`:

1. treat current files as the source of truth;
2. use the working state as a handoff and pointer map, not as a substitute for the repository;
3. reread relevant files before making non-trivial edits.

# Scope rule

Do not create or reuse one global task-state file across unrelated repositories. Keep task state project-local so goals, decisions, failures, and next actions cannot bleed between projects.
