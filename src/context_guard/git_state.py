"""Best-effort Git inspection used by Context Guard."""

from __future__ import annotations

import subprocess
from pathlib import Path


GIT_TIMEOUT_SECONDS = 3


def _run_git(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("git command failed")
    return result.stdout.strip()


def _git_returncode(cwd: Path, args: list[str]) -> int | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode


def repository_root(cwd: Path) -> Path | None:
    """Resolve only the Git worktree root without running status."""
    try:
        raw = _run_git(Path(cwd), ["rev-parse", "--show-toplevel"])
        return Path(raw).resolve() if raw else None
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return None


def collect(cwd: Path) -> dict:
    empty = {
        "is_repo": False,
        "root": None,
        "branch": None,
        "head": None,
        "status_short": None,
    }
    try:
        root = _run_git(Path(cwd), ["rev-parse", "--show-toplevel"])
        branch = _run_git(Path(cwd), ["branch", "--show-current"]) or None
        head = _run_git(Path(cwd), ["rev-parse", "HEAD"]) or None
        status = _run_git(Path(cwd), ["status", "--short"])
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return empty
    return {
        "is_repo": True,
        "root": root or None,
        "branch": branch,
        "head": head,
        "status_short": status,
    }


def context_guard_git_safety(project_root: Path) -> tuple[bool | None, list[str]]:
    """Check that local runtime artifacts cannot be accidentally committed.

    Returns (None, []) for non-Git projects. For Git projects the bool is true
    only when the working-state file and session tree are effectively ignored
    and no runtime artifact is already tracked.
    """
    project_root = Path(project_root).resolve()
    git_root = repository_root(project_root)
    if git_root is None:
        return None, []

    guard = project_root / ".claude" / "context-guard"
    try:
        relative_guard = guard.relative_to(git_root)
    except ValueError:
        return False, ["context-guard root is outside the Git worktree"]

    working_state = relative_guard / "WORKING_STATE.md"
    sessions_probe = relative_guard / "sessions" / ".context-guard-ignore-probe"
    problems: list[str] = []

    for label, path in (("WORKING_STATE.md", working_state), ("sessions/", sessions_probe)):
        result = _git_returncode(
            git_root,
            ["check-ignore", "--no-index", "-q", "--", str(path)],
        )
        if result != 0:
            problems.append(f"not ignored: {label}")

    try:
        tracked = _run_git(
            git_root,
            ["ls-files", "--", str(working_state), str(relative_guard / "sessions")],
        )
    except (OSError, RuntimeError, subprocess.SubprocessError):
        problems.append("unable to verify tracked runtime files")
    else:
        if tracked:
            problems.append("runtime artifacts are already tracked by Git")

    return not problems, problems


def render(info: dict, limit: int = 2000) -> str:
    if limit <= 0:
        return ""
    if not info.get("is_repo"):
        rendered = "Git: not a repository."
    else:
        status = info.get("status_short") or "clean"
        rendered = "\n".join(
            (
                "Git repository: yes",
                f"Root: {info.get('root') or 'unknown'}",
                f"Branch: {info.get('branch') or 'detached/unknown'}",
                f"HEAD: {info.get('head') or 'unknown'}",
                "Status (short):",
                status,
            )
        )
    if len(rendered) <= limit:
        return rendered
    marker = "\n[git state truncated]"
    if len(marker) >= limit:
        return marker[:limit]
    return rendered[: max(0, limit - len(marker))] + marker
