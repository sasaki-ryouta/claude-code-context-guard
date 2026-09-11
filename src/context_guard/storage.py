"""Safe, atomic persistence beneath a project's context-guard directory."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


_SAFE_SESSION = re.compile(r"[^A-Za-z0-9._-]")
_FALLBACK_SESSION = "session-unknown"


def guard_root(project_root: Path) -> Path:
    return Path(project_root) / ".claude" / "context-guard"


def safe_session_id(raw) -> str:
    if not isinstance(raw, str) or raw == "":
        return _FALLBACK_SESSION
    safe = _SAFE_SESSION.sub("_", raw)
    if safe in {"", ".", ".."}:
        return _FALLBACK_SESSION
    return safe


def session_dir(project_root: Path, session_id) -> Path:
    root = guard_root(Path(project_root))
    candidate = root / "sessions" / safe_session_id(session_id)
    resolved_root = root.resolve()
    if not candidate.resolve().is_relative_to(resolved_root):
        raise ValueError("session directory escaped the guard root")
    return candidate


def compactions_dir(project_root: Path, session_id) -> Path:
    return session_dir(project_root, session_id) / "compactions"


def compaction_dir(project_root: Path, session_id, sequence: int) -> Path:
    if not isinstance(sequence, int) or sequence < 1:
        raise ValueError("compaction sequence must be a positive integer")
    return compactions_dir(project_root, session_id) / f"{sequence:06d}"


def _compaction_sequences(project_root: Path, session_id) -> list[int]:
    directory = compactions_dir(project_root, session_id)
    if not directory.is_dir():
        return []
    sequences: list[int] = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.is_dir() and len(entry.name) == 6 and entry.name.isdigit():
            value = int(entry.name)
            if value > 0:
                sequences.append(value)
    return sequences


def next_compaction_sequence(project_root: Path, session_id) -> int:
    sequences = _compaction_sequences(project_root, session_id)
    return (max(sequences) if sequences else 0) + 1


def latest_compaction_sequence(project_root: Path, session_id) -> int | None:
    sequences = _compaction_sequences(project_root, session_id)
    return max(sequences) if sequences else None


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


def append_event(project_root: Path, session_id, event: dict) -> None:
    directory = session_dir(project_root, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    events_path = _assert_guard_path(directory / "events.jsonl")
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(events_path, "a", encoding="utf-8", newline="") as handle:
        handle.write(line)
