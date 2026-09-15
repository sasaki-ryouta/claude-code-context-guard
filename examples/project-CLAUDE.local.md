# Project-local working state

Use `.claude/context-guard/WORKING_STATE.md` as the working-state file for this project.

Maintain it according to the working-state and compaction policy from my user-level Claude instructions.

For this project:

- keep the file concise and pointer-rich;
- update it only at semantic boundaries and before a deliberate `/compact`;
- do not write secrets or credentials into it;
- do not treat it as a source-of-truth replacement for the repository;
- if the file is absent, create it from the project's chosen working-state template before relying on it.

The expected sections are:

- Goal
- Acceptance criteria
- Current phase
- Decisions
- Current failures
- Next
- Pointers
- Notes only when necessary
