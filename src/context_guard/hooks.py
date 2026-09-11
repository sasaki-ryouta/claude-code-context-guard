"""Claude Code hook handlers. Every handler is deliberately fail-open."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import git_state, state, storage
from .models import Checkpoint, WorkingStateRecord


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cwd(payload: dict) -> Path:
    raw = payload.get("cwd")
    if isinstance(raw, str) and raw:
        return Path(raw)
    return Path.cwd()


def _transcript_path(payload: dict) -> str | None:
    raw = payload.get("transcript_path")
    return raw if isinstance(raw, str) else None


def _record_error(cwd: Path, session_id, error: Exception) -> None:
    try:
        storage.append_event(
            cwd,
            session_id,
            {
                "event": "hook_error",
                "timestamp": _timestamp(),
                "error_type": type(error).__name__,
            },
        )
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
        f"- trigger: {checkpoint['trigger']}",
        f"- cwd: {checkpoint['cwd']}",
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
    cwd = _cwd(payload)
    session_id = payload.get("session_id")
    try:
        working_path = state.working_state_path(cwd)
        current_state = state.read_working_state(cwd)
        working = WorkingStateRecord(
            exists=current_state is not None,
            path=str(working_path),
            chars=len(current_state) if current_state is not None else 0,
            sha256=state.sha256_text(current_state) if current_state is not None else None,
            snapshot=current_state,
        )
        checkpoint = Checkpoint(
            schema_version=1,
            event="pre_compact",
            timestamp=_timestamp(),
            session_id=session_id,
            safe_session_id=storage.safe_session_id(session_id),
            trigger=payload.get("trigger"),
            cwd=str(cwd),
            transcript_path=_transcript_path(payload),
            git=git_state.collect(cwd),
            working_state=working,
        )
        data = asdict(checkpoint)
        session = storage.session_dir(cwd, session_id)
        storage.atomic_write_text(
            session / "checkpoint.json",
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        )
        storage.atomic_write_text(session / "checkpoint.md", _checkpoint_markdown(data))
        event = {
            "event": "pre_compact",
            "timestamp": data["timestamp"],
            "session_id": session_id,
            "trigger": payload.get("trigger"),
            "state_chars": working.chars,
            "state_sha256": working.sha256,
            "branch": data["git"]["branch"],
            "head": data["git"]["head"],
        }
        storage.append_event(cwd, session_id, event)
    except Exception as error:
        _record_error(cwd, session_id, error)
    return {}


def handle_session_start(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("source") != "compact":
        return {}
    cwd = _cwd(payload)
    session_id = payload.get("session_id")
    try:
        context = state.build_recovery_context(cwd)
    except Exception as error:
        _record_error(cwd, session_id, error)
        return {}
    try:
        storage.append_event(
            cwd,
            session_id,
            {
                "event": "rehydrate",
                "timestamp": _timestamp(),
                "session_id": session_id,
                "source": "compact",
                "context_chars": len(context),
                "context_sha256": state.sha256_text(context),
            },
        )
    except Exception:
        # Losing the observability record must never lose the rehydration.
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
    cwd = _cwd(payload)
    session_id = payload.get("session_id")
    try:
        summary = payload.get("compact_summary")
        has_summary = isinstance(summary, str)
        session = storage.session_dir(cwd, session_id)
        if has_summary:
            storage.atomic_write_text(session / "compact-summary.md", summary)
            summary_chars = len(summary)
            summary_sha256 = state.sha256_text(summary)
        else:
            summary_chars = 0
            summary_sha256 = None
        storage.append_event(
            cwd,
            session_id,
            {
                "event": "post_compact",
                "timestamp": _timestamp(),
                "session_id": session_id,
                "trigger": payload.get("trigger"),
                "summary_chars": summary_chars,
                "summary_sha256": summary_sha256,
            },
        )
    except Exception as error:
        _record_error(cwd, session_id, error)
    return {}

