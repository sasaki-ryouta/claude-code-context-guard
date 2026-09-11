"""Working-state loading, hashing, and bounded recovery-context assembly."""

from __future__ import annotations

import hashlib
from pathlib import Path


WORKING_STATE_BUDGET = 6000
GIT_BUDGET = 2000
RECOVERY_BUDGET = 1000
TOTAL_BUDGET = 9000
TRUNCATION_MARKER = "\n[WORKING_STATE truncated]"

_RECOVERY_INSTRUCTIONS = (
    "This is external working state restored after context compaction.\n\n"
    "Treat the current filesystem as source of truth.\n"
    "The state below contains goals, decisions, unresolved failures, next actions,\n"
    "and pointers; it is not a substitute for rereading relevant source files."
)


def working_state_path(project_root: Path) -> Path:
    from .storage import guard_root

    return guard_root(Path(project_root)) / "WORKING_STATE.md"


def read_working_state(project_root: Path) -> str | None:
    path = working_state_path(project_root)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate_state(text: str, limit: int = WORKING_STATE_BUDGET) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    if limit <= 0:
        return "", True
    marker = TRUNCATION_MARKER
    if len(marker) >= limit:
        return marker[:limit], True
    return text[: limit - len(marker)] + marker, True


def build_recovery_context(project_root: Path, git_cwd: Path | None = None) -> str:
    from . import git_state

    project_root = Path(project_root)
    state_text = read_working_state(project_root)
    git_text = git_state.render(
        git_state.collect(Path(git_cwd) if git_cwd is not None else project_root),
        GIT_BUDGET,
    )
    if state_text is None:
        context = (
            f"{_RECOVERY_INSTRUCTIONS}\n\n"
            "No WORKING_STATE.md is present; recover from the current filesystem.\n\n"
            f"Current git state:\n{git_text}"
        )
    else:
        full_path = str(working_state_path(project_root))
        truncation_note = f"\nFull WORKING_STATE.md: {full_path}"
        state_limit = max(1, WORKING_STATE_BUDGET - len(truncation_note))
        bounded_state, truncated = truncate_state(state_text, state_limit)
        if truncated:
            bounded_state += truncation_note
        context = (
            f"{_RECOVERY_INSTRUCTIONS}\n\n"
            f"WORKING_STATE.md:\n{bounded_state}\n\n"
            f"Current git state:\n{git_text}"
        )
    if len(context) <= TOTAL_BUDGET:
        return context
    return context[:TOTAL_BUDGET]
