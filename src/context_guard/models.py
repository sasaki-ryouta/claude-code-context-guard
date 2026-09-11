"""Small data models used by the hook persistence layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkingStateRecord:
    exists: bool
    path: str
    chars: int
    sha256: str | None
    snapshot: str | None


@dataclass(frozen=True)
class Checkpoint:
    schema_version: int
    event: str
    timestamp: str
    session_id: object
    safe_session_id: str
    compaction_sequence: int
    trigger: object
    cwd: str
    project_root: str
    transcript_path: str | None
    git: dict
    working_state: WorkingStateRecord
