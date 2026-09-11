"""Command-line adapter for Claude Code hook stdin/stdout."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from . import git_state, hooks, state


_HOOKS = {
    "pre-compact": hooks.handle_pre_compact,
    "session-start": hooks.handle_session_start,
    "post-compact": hooks.handle_post_compact,
}


def _read_payload() -> dict | None:
    # A pathological payload raises things no narrow except tuple predicts:
    # RecursionError from the recursive decoder, MemoryError from a huge read.
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _run_hook(command: str) -> int:
    try:
        payload = _read_payload()
        if payload is None:
            return 0
        output = _HOOKS[command](payload)
        if isinstance(output, dict) and output:
            sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


def _doctor() -> int:
    cwd = Path.cwd()
    problems = False

    python_ok = sys.version_info >= (3, 11)
    print(f"Python version: {sys.version.split()[0]} ({'ok' if python_ok else 'unsupported'})")
    problems |= not python_ok

    root_ok = cwd.is_dir()
    print(f"Project root: {cwd} ({'ok' if root_ok else 'missing'})")
    problems |= not root_ok

    working_path = state.working_state_path(cwd)
    if not working_path.is_file():
        print(f"WORKING_STATE: missing ({working_path})")
    else:
        chars = len(state.read_working_state(cwd) or "")
        budget_ok = chars <= state.WORKING_STATE_BUDGET
        print(
            f"WORKING_STATE: {chars} characters "
            f"({'ok' if budget_ok else 'over budget'})"
        )
        problems |= not budget_ok

    settings_paths = (cwd / ".claude" / "settings.json", cwd / ".claude" / "settings.local.json")
    settings_ok = False
    for settings_path in settings_paths:
        if not settings_path.is_file():
            continue
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings_ok = isinstance(settings, dict) and isinstance(settings.get("hooks"), dict)
        except (OSError, UnicodeError, json.JSONDecodeError):
            settings_ok = False
        if settings_ok:
            break
    print(f"Hook configuration: {'present' if settings_ok else 'missing or invalid'}")
    problems |= not settings_ok

    try:
        importlib.import_module("context_guard")
        importable = True
    except Exception:
        importable = False
    print(f"Importability: {'ok' if importable else 'failed'}")
    problems |= not importable

    git = git_state.collect(cwd)
    if git["is_repo"] and git["status_short"] is not None:
        print("Git status: available")
    elif git["is_repo"]:
        print("Git status: unavailable")
        problems = True
    else:
        print("Git status: not a git repository (not applicable)")

    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    command = arguments[0] if arguments else ""
    if command == "doctor":
        try:
            return _doctor()
        except Exception:
            return 1
    if command in _HOOKS:
        return _run_hook(command)
    return 0

