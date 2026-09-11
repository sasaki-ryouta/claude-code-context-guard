"""Command-line adapter for Claude Code hook stdin/stdout."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

from . import git_state, hooks, project, state


_HOOKS = {
    "pre-compact": hooks.handle_pre_compact,
    "session-start": hooks.handle_session_start,
    "post-compact": hooks.handle_post_compact,
}

_REQUIRED_HOOKS = {
    "PreCompact": ({"manual", "auto"}, "pre-compact"),
    "SessionStart": ({"compact"}, "session-start"),
    "PostCompact": ({"manual", "auto"}, "post-compact"),
}


def _read_payload() -> dict | None:
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
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if project_dir:
            payload["_context_guard_project_dir"] = project_dir
        output = _HOOKS[command](payload)
        if isinstance(output, dict) and output:
            sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


def _matcher_tokens(raw: object) -> set[str]:
    if not isinstance(raw, str):
        return set()
    return {part.strip() for part in raw.split("|") if part.strip()}


def _has_expected_hook(settings: dict, event: str, matcher: set[str], subcommand: str) -> bool:
    hooks_config = settings.get("hooks")
    if not isinstance(hooks_config, dict):
        return False
    groups = hooks_config.get(event)
    if not isinstance(groups, list):
        return False
    for group in groups:
        if not isinstance(group, dict):
            continue
        if _matcher_tokens(group.get("matcher")) != matcher:
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") != "command":
                continue
            command = entry.get("command")
            if isinstance(command, str) and "context_guard" in command and subcommand in command:
                return True
    return False


def _validate_settings(settings: object) -> tuple[bool, list[str]]:
    if not isinstance(settings, dict):
        return False, ["top-level JSON is not an object"]
    missing: list[str] = []
    for event, (matcher, subcommand) in _REQUIRED_HOOKS.items():
        if not _has_expected_hook(settings, event, matcher, subcommand):
            missing.append(event)
    return not missing, missing


def _doctor() -> int:
    cwd = Path.cwd()
    problems = False
    project_root = project.resolve_project_root(cwd, os.environ.get("CLAUDE_PROJECT_DIR"))

    python_ok = sys.version_info >= (3, 11)
    print(f"Python version: {sys.version.split()[0]} ({'ok' if python_ok else 'unsupported'})")
    problems |= not python_ok

    root_ok = project_root.is_dir()
    print(f"Project root: {project_root} ({'ok' if root_ok else 'missing'})")
    problems |= not root_ok

    working_path = state.working_state_path(project_root)
    if not working_path.is_file():
        print(f"WORKING_STATE: missing ({working_path})")
        problems = True
    else:
        chars = len(state.read_working_state(project_root) or "")
        budget_ok = chars <= state.WORKING_STATE_BUDGET
        print(f"WORKING_STATE: {chars} characters ({'ok' if budget_ok else 'over budget'})")
        problems |= not budget_ok

    settings_paths = (
        project_root / ".claude" / "settings.json",
        project_root / ".claude" / "settings.local.json",
    )
    settings_ok = False
    settings_detail = "missing"
    for settings_path in settings_paths:
        if not settings_path.is_file():
            continue
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            valid, missing = _validate_settings(settings)
        except (OSError, UnicodeError, json.JSONDecodeError):
            valid, missing = False, ["invalid JSON"]
        if valid:
            settings_ok = True
            settings_detail = str(settings_path)
            break
        settings_detail = f"{settings_path}: missing/invalid {', '.join(missing)}"
    print(f"Hook configuration: {'ok' if settings_ok else 'invalid'} ({settings_detail})")
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

    ignore_ok, ignore_problems = git_state.context_guard_git_safety(project_root)
    if ignore_ok is None:
        print("Runtime gitignore: not applicable (non-git project)")
    elif ignore_ok:
        print("Runtime gitignore: ok")
    else:
        print(f"Runtime gitignore: unsafe ({'; '.join(ignore_problems)})")
        problems = True

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
