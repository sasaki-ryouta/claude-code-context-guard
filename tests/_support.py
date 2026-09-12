"""Shared test helpers. No third-party imports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def load_fixture(name: str, **overrides) -> dict:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    payload.update(overrides)
    return payload


def run_cli(
    command: str,
    stdin_text: str,
    *,
    extra_env: dict[str, str] | None = None,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if extra_env:
        env.update(extra_env)
    env["PYTHONPATH"] = str(SRC_DIR)
    # A payload without "cwd" makes the hook fall back to the process cwd.
    # Inheriting the developer's cwd would write into this repository, so
    # every run gets a throwaway directory unless the caller names one.
    with tempfile.TemporaryDirectory() as scratch:
        return subprocess.run(
            [sys.executable, "-m", "context_guard", command],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd) if cwd is not None else scratch,
            timeout=60,
        )


def init_git_repo(path: Path) -> None:
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME":"test","GIT_AUTHOR_EMAIL":"test@example.com","GIT_COMMITTER_NAME":"test","GIT_COMMITTER_EMAIL":"test@example.com"})
    for args in (["init","-q","-b","work"],["commit","-q","--allow-empty","-m","root"]):
        subprocess.run(["git", *args], cwd=path, env=env, check=True, capture_output=True)


def write_working_state(project_root: Path, text: str) -> Path:
    target = project_root / ".claude" / "context-guard" / "WORKING_STATE.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def write_valid_settings(project_root: Path) -> Path:
    source = REPO_ROOT / ".claude" / "settings.example.json"
    target = project_root / ".claude" / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def write_runtime_gitignore(project_root: Path) -> Path:
    target = project_root / ".gitignore"
    target.write_text(
        ".claude/context-guard/WORKING_STATE.md\n"
        ".claude/context-guard/sessions/\n",
        encoding="utf-8",
    )
    return target


SAMPLE_STATE = """# Goal

Scaffold context-guard v0.1.

# Acceptance criteria

- all tests pass

# Current phase

Implementation

# Decisions

- Keep durable state small
  - Why: filesystem is source of truth
  - Affects: hooks.py

# Current failures

- Failure: none

# Next

- run the test suite

# Pointers

- file: src/context_guard/hooks.py
"""
