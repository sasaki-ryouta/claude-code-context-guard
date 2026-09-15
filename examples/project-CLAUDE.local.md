# Project-local working state

Use `WORKING_STATE.local.md` as the working-state file for this checkout.

Maintain it according to the working-state and compaction policy from my user-level Claude instructions.

For this project:

- keep the file concise and pointer-rich;
- update it only at semantic boundaries and before a deliberate `/compact`;
- do not write secrets or credentials into it;
- do not treat it as a source-of-truth replacement for the repository;
- treat it as current-task handoff state, not as a duplicate of durable Auto Memory;
- keep both `CLAUDE.local.md` and `WORKING_STATE.local.md` checkout-local and out of Git;
- if the state file is absent, create it from the project's chosen working-state template before relying on it.

The expected sections are:

- Goal
- Acceptance criteria
- Current phase
- Decisions
- Current failures
- Next
- Pointers
- Notes only when necessary

If this project later installs Context Guard hooks, follow the Context Guard setup and use its supported `.claude/context-guard/WORKING_STATE.md` runtime path instead.