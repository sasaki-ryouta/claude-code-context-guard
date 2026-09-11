"""Best-effort collection of the small amount of git state used by recovery."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("git command failed")
    return result.stdout.strip()


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
