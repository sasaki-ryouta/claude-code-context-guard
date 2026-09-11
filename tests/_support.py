"""Shared test helpers. No third-party imports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def run_cli(command: str, stdin_text: str) -> subprocess.CompletedProcess:
    """Run the hook entrypoint exactly the way Claude Code would."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [sys.executable, "-m", "context_guard", command],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def init_git_repo(path: Path) -> None:
    """Create a throwaway git repo with one commit, or skip the caller's git expectations."""
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    for args in (
        ["init", "-q", "-b", "work"],
        ["commit", "-q", "--allow-empty", "-m", "root"],
    ):
        subprocess.run(
            ["git", *args], cwd=path, env=env, check=True, capture_output=True
        )


def write_working_state(cwd: Path, text: str) -> Path:
    target = cwd / ".claude" / "context-guard" / "WORKING_STATE.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
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
