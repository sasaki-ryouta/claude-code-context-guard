"""Claude Code hook handlers. Every handler is deliberately fail-open."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import git_state, project, state, storage
from .models import Checkpoint, WorkingStateRecord


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cwd(payload: dict) -> Path:
    raw = payload.get("cwd")
    if isinstance(raw, str) and raw:
        return Path(raw)
    return Path.cwd()


def _project_root(payload: dict, cwd: Path) -> Path:
    return project.resolve_project_root(cwd, payload.get("_context_guard_project_dir"))


def _transcript_path(payload: dict) -> str | None:
    raw = payload.get("transcript_path")
    return raw if isinstance(raw, str) else None


def _duration_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)


def _record_error(
    project_root: Path,
    session_id,
    error: Exception,
    *,
    cwd: Path | None = None,
    started: float | None = None,
) -> None:
    try:
        event = {
            "event": "hook_error",
            "timestamp": _timestamp(),
            "session_id": session_id,
            "error_type": type(error).__name__,
            "project_root": str(project_root),
        }
        if cwd is not None:
            event["cwd"] = str(cwd)
        if started is not None:
            event["duration_ms"] = _duration_ms(started)
        storage.append_event(project_root, session_id, event)
    except Exception:
        pass


def _checkpoint_markdown(checkpoint: dict) -> str:
    git = checkpoint["git"]
    working = checkpoint["working_state"]
    lines = [
        "# PreCompact checkpoint",
        f"- schema_version: {checkpoint['schema_version']}",
        f"- event: {checkpoint['event']}",
        f"- timestamp: {checkpoint['timestamp']}",
        f"- session_id: {checkpoint['session_id']}",
        f"- safe_session_id: {checkpoint['safe_session_id']}",
        f"- compaction_sequence: {checkpoint['compaction_sequence']}",
        f"- trigger: {checkpoint['trigger']}",
        f"- cwd: {checkpoint['cwd']}",
        f"- project_root: {checkpoint['project_root']}",
        f"- transcript_path: {checkpoint['transcript_path']}",
        "- git:",
        f"  - is_repo: {git['is_repo']}",
        f"  - root: {git['root']}",
        f"  - branch: {git['branch']}",
        f"  - head: {git['head']}",
        f"  - status_short: {git['status_short']}",
        "- working_state:",
        f"  - exists: {working['exists']}",
        f"  - path: {working['path']}",
        f"  - chars: {working['chars']}",
        f"  - sha256: {working['sha256']}",
        "",
    ]
    if working["snapshot"] is not None:
        lines += ["## WORKING_STATE snapshot", "", working["snapshot"], ""]
    return "\n".join(lines)


def handle_pre_compact(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    started = time.monotonic()
    cwd = _cwd(payload)
    project_root = cwd
    session_id = payload.get("session_id")
    try:
        project_root = _project_root(payload, cwd)
        working_path = state.working_state_path(project_root)
        current_state = state.read_working_state(project_root)
        working = WorkingStateRecord(
            exists=current_state is not None,
            path=str(working_path),
            chars=len(current_state) if current_state is not None else 0,
            sha256=state.sha256_text(current_state) if current_state is not None else None,
            snapshot=current_state,
        )
        sequence = storage.next_compaction_sequence(project_root, session_id)
        checkpoint = Checkpoint(
            schema_version=2,
            event="pre_compact",
            timestamp=_timestamp(),
            session_id=session_id,
            safe_session_id=storage.safe_session_id(session_id),
            compaction_sequence=sequence,
            trigger=payload.get("trigger"),
            cwd=str(cwd),
            project_root=str(project_root),
            transcript_path=_transcript_path(payload),
            git=git_state.collect(cwd),
            working_state=working,
        )
        data = asdict(checkpoint)
        checkpoint_json = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        checkpoint_md = _checkpoint_markdown(data)
        session = storage.session_dir(project_root, session_id)
        archived = storage.compaction_dir(project_root, session_id, sequence)

        storage.atomic_write_text(archived / "checkpoint.json", checkpoint_json)
        storage.atomic_write_text(archived / "checkpoint.md", checkpoint_md)
        storage.atomic_write_text(session / "checkpoint.json", checkpoint_json)
        storage.atomic_write_text(session / "checkpoint.md", checkpoint_md)

        storage.append_event(
            project_root,
            session_id,
            {
                "event": "pre_compact",
                "timestamp": data["timestamp"],
                "session_id": session_id,
                "compaction_sequence": sequence,
                "trigger": payload.get("trigger"),
                "cwd": str(cwd),
                "project_root": str(project_root),
                "state_chars": working.chars,
                "state_sha256": working.sha256,
                "branch": data["git"]["branch"],
                "head": data["git"]["head"],
                "duration_ms": _duration_ms(started),
            },
        )
    except Exception as error:
        _record_error(project_root, session_id, error, cwd=cwd, started=started)
    return {}


def handle_session_start(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("source") != "compact":
        return {}
    started = time.monotonic()
    cwd = _cwd(payload)
    project_root = cwd
    session_id = payload.get("session_id")
    try:
        project_root = _project_root(payload, cwd)
        context = state.build_recovery_context(project_root, git_cwd=cwd)
        sequence = storage.latest_compaction_sequence(project_root, session_id)
    except Exception as error:
        _record_error(project_root, session_id, error, cwd=cwd, started=started)
        return {}
    try:
        storage.append_event(
            project_root,
            session_id,
            {
                "event": "rehydrate",
                "timestamp": _timestamp(),
                "session_id": session_id,
                "compaction_sequence": sequence,
                "source": "compact",
                "cwd": str(cwd),
                "project_root": str(project_root),
                "context_chars": len(context),
                "context_sha256": state.sha256_text(context),
                "duration_ms": _duration_ms(started),
            },
        )
    except Exception:
        pass
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }


def handle_post_compact(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    started = time.monotonic()
    cwd = _cwd(payload)
    project_root = cwd
    session_id = payload.get("session_id")
    try:
        project_root = _project_root(payload, cwd)
        summary = payload.get("compact_summary")
        has_summary = isinstance(summary, str)
        session = storage.session_dir(project_root, session_id)
        sequence = storage.latest_compaction_sequence(project_root, session_id)
        if has_summary:
            storage.atomic_write_text(session / "compact-summary.md", summary)
            if sequence is not None:
                archived_summary = (
                    storage.compaction_dir(project_root, session_id, sequence)
                    / "compact-summary.md"
                )
                if not archived_summary.exists():
                    storage.atomic_write_text(archived_summary, summary)
            summary_chars = len(summary)
            summary_sha256 = state.sha256_text(summary)
        else:
            summary_chars = 0
            summary_sha256 = None
        storage.append_event(
            project_root,
            session_id,
            {
                "event": "post_compact",
                "timestamp": _timestamp(),
                "session_id": session_id,
                "compaction_sequence": sequence,
                "trigger": payload.get("trigger"),
                "cwd": str(cwd),
                "project_root": str(project_root),
                "summary_chars": summary_chars,
                "summary_sha256": summary_sha256,
                "duration_ms": _duration_ms(started),
            },
        )
    except Exception as error:
        _record_error(project_root, session_id, error, cwd=cwd, started=started)
    return {}
