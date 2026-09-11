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

    Claude Code exposes CLAUDE_PROJECT_DIR to hook commands. The CLI copies
    that value into an internal payload field before dispatching, keeping the
    hook handlers deterministic and easy to test. Direct/manual invocation
    falls back to the current Git worktree root, then cwd.
    """
    cwd = Path(cwd)

    hinted = _directory_hint(cwd, project_dir_hint)
    if hinted is not None:
        return hinted

    info = git_state.collect(cwd)
    root = info.get("root")
    if info.get("is_repo") and isinstance(root, str) and root:
        try:
            return Path(root).resolve()
        except OSError:
            pass

    try:
        return cwd.resolve()
    except OSError:
        return cwd.absolute()
