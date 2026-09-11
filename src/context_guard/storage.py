"""Safe, atomic persistence beneath a project's context-guard directory."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


_SAFE_SESSION = re.compile(r"[^A-Za-z0-9._-]")
_FALLBACK_SESSION = "session-unknown"


def guard_root(cwd: Path) -> Path:
    return Path(cwd) / ".claude" / "context-guard"


def safe_session_id(raw) -> str:
    if not isinstance(raw, str) or raw == "":
        return _FALLBACK_SESSION
    safe = _SAFE_SESSION.sub("_", raw)
    if safe in {"", ".", ".."}:
        return _FALLBACK_SESSION
    return safe


def session_dir(cwd: Path, session_id) -> Path:
    root = guard_root(Path(cwd))
    candidate = root / "sessions" / safe_session_id(session_id)
    resolved_root = root.resolve()
    if not candidate.resolve().is_relative_to(resolved_root):
        raise ValueError("session directory escaped the guard root")
    return candidate


def _assert_guard_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    parts = resolved.parts
    for index in range(len(parts) - 1):
        if parts[index : index + 2] == (".claude", "context-guard"):
            root = Path(*parts[: index + 2])
            if resolved.is_relative_to(root):
                return resolved
    raise ValueError("writes are restricted to .claude/context-guard")


def atomic_write_text(path: Path, text: str) -> None:
    target = _assert_guard_path(Path(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".tmp-", dir=str(target.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def append_event(cwd: Path, session_id, event: dict) -> None:
    directory = session_dir(cwd, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    events_path = _assert_guard_path(directory / "events.jsonl")
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(events_path, "a", encoding="utf-8", newline="") as handle:
        handle.write(line)
