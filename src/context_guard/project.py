"""Stable project-root resolution for hook runtime state."""

from __future__ import annotations

from pathlib import Path

from . import git_state


def _directory_hint(cwd: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def resolve_project_root(cwd: Path, project_dir_hint: object = None) -> Path:
    """Resolve the stable root used for Context Guard state.

    Prefer Claude Code's project directory. Direct/manual invocation falls
    back to one cheap `git rev-parse --show-toplevel`, then cwd. Root
    resolution deliberately does not run `git status`; full Git telemetry is
    collected only by hook paths that actually need it.
    """
    cwd = Path(cwd)

    hinted = _directory_hint(cwd, project_dir_hint)
    if hinted is not None:
        return hinted

    root = git_state.repository_root(cwd)
    if root is not None:
        return root

    try:
        return cwd.resolve()
    except OSError:
        return cwd.absolute()
