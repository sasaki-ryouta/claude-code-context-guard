from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .materialize import materialize
from .score_markers import load_markers, score_text


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
MANIFEST_PATH = HERE / "manifest.json"
PROMPTS_PATH = HERE / "prompts.json"
AUTO_COMPACT_WINDOW = "1000000"
COMPACT_AFTER_TURN = 14
# The orientation prompt is not a scripted turn: docs/benchmark-fixture-v1.md
# numbers "Turn 1" as the first entry of prompts.json -> turns.
INITIAL_TURN = 0
STATE_RECORDED_TURN = 2
FINAL_PRE_COMPACT_TURNS = 8


def is_post_state_turn(turn_number: int) -> bool:
    """Turns counted toward SPEC 8 rule 2 (>= 12 substantive turns after state)."""
    return STATE_RECORDED_TURN < turn_number <= COMPACT_AFTER_TURN


def is_final_pre_compact_turn(turn_number: int) -> bool:
    """The final eight pre-compact turns (SPEC 8 rules 3 and 4)."""
    first = COMPACT_AFTER_TURN - FINAL_PRE_COMPACT_TURNS + 1
    return first <= turn_number <= COMPACT_AFTER_TURN


def fixture_source_commit() -> str:
    """HEAD of this checkout: the harness/fixture revision a run came from."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()
TURN_TIMEOUT_SECONDS = 300
ARMS = ("A", "B", "C", "D")
WORK_ALLOWED_TOOLS: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash",
    "TodoWrite",
)
PROBE_DISALLOWED_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "Task",
    "WebFetch",
    "WebSearch",
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def arm_config(arm: str) -> dict[str, bool]:
    configs = {
        "A": {"working_state": False, "hooks": False, "claude_md": False},
        "B": {"working_state": True, "hooks": False, "claude_md": True},
        "C": {"working_state": True, "hooks": True, "claude_md": True},
        "D": {"working_state": False, "hooks": True, "claude_md": False},
    }
    try:
        return dict(configs[arm])
    except KeyError as error:
        raise ValueError(f"unknown arm: {arm}") from error


def _hook_command(context_guard_root: Path, subcommand: str) -> str:
    source = str((context_guard_root.resolve() / "src")).replace('"', '\\"')
    return f'PYTHONPATH="{source}" python3 -m context_guard {subcommand}'


def _settings(context_guard_root: Path) -> dict[str, Any]:
    def hook(event: str, matcher: str, command: str, status: str) -> dict[str, Any]:
        return {
            event: [
                {
                    "matcher": matcher,
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_command(context_guard_root, command),
                            "timeout": 15,
                            "statusMessage": status,
                        }
                    ],
                }
            ]
        }

    settings: dict[str, Any] = {"hooks": {}}
    settings["hooks"].update(
        hook(
            "PreCompact",
            "manual|auto",
            "pre-compact",
            "context-guard: checkpointing working state",
        )
    )
    settings["hooks"].update(
        hook(
            "SessionStart",
            "compact",
            "session-start",
            "context-guard: restoring working state",
        )
    )
    settings["hooks"].update(
        hook(
            "PostCompact",
            "manual|auto",
            "post-compact",
            "context-guard: persisting compaction summary",
        )
    )
    return settings


def prepare_target(arm: str, destination: Path, context_guard_root: Path) -> dict[str, Any]:
    config = arm_config(arm)
    target = Path(destination).resolve()
    initial_commit = materialize(target)
    assets = Path(context_guard_root).resolve() / "benchmarks" / "fixture_v1" / "arm_assets"

    if config["claude_md"]:
        shutil.copyfile(assets / "CLAUDE.md", target / "CLAUDE.md")
    if config["working_state"]:
        state_path = target / ".claude" / "context-guard" / "WORKING_STATE.md"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / "WORKING_STATE.md", state_path)
    if config["hooks"]:
        settings_path = target / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(_settings(Path(context_guard_root)), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return {
        "target": target,
        "initial_commit": initial_commit,
        "arm": arm,
        **config,
    }


def _prompt_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def prompt_hashes(prompts: dict) -> dict[str, Any]:
    turns = prompts.get("turns")
    if not isinstance(prompts.get("initial"), str) or not isinstance(turns, list):
        raise ValueError("prompts must contain an initial string and turns list")
    values = {"initial": _prompt_hash(prompts["initial"]), "turns": []}
    for turn in turns:
        if not isinstance(turn, str):
            raise ValueError("every scripted turn must be a string")
        values["turns"].append(_prompt_hash(turn))
    for key in ("probe", "resume"):
        if not isinstance(prompts.get(key), str):
            raise ValueError(f"prompts must contain a {key} string")
        values[key] = _prompt_hash(prompts[key])
    return values


def prompt_marker_leaks(prompts: dict, markers: dict[str, str]) -> list[str]:
    leaks: list[str] = []
    fields: list[tuple[str, object]] = [
        ("initial", prompts.get("initial")),
        *( (f"turns[{index}]", value) for index, value in enumerate(prompts.get("turns", [])) ),
        ("probe", prompts.get("probe")),
        ("resume", prompts.get("resume")),
    ]
    for label, value in fields:
        if not isinstance(value, str):
            continue
        for token in markers.values():
            if token in value:
                leaks.append(f"{label}: {token}")
    return leaks


def _tool_uses(events: list[dict]) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        candidates: list[object] = []
        if event.get("type") == "tool_use":
            candidates.append(event)
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                candidates.extend(content)
        content = event.get("content")
        if isinstance(content, list):
            candidates.extend(content)
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("type") != "tool_use":
                continue
            name = candidate.get("name")
            if isinstance(name, str):
                payload = candidate.get("input")
                found.append((name, payload if isinstance(payload, dict) else {}))
    return found


def _marker_material(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        "docs/contract.md" in normalized
        or "docs/incident.md" in normalized
        or normalized.endswith("WORKING_STATE.md")
        or "/WORKING_STATE.md" in normalized
    )


def analyze_turn(events: list[dict]) -> dict[str, Any]:
    uses = _tool_uses(events)
    marker_reads: list[str] = []
    for name, payload in uses:
        if name == "Read":
            file_path = payload.get("file_path")
            if isinstance(file_path, str) and _marker_material(file_path):
                marker_reads.append(file_path)
        elif name == "Bash":
            command = payload.get("command")
            if isinstance(command, str) and _marker_material(command):
                marker_reads.append(command)
    return {
        "tool_uses": len(uses),
        "tools": [name for name, _ in uses],
        "marker_bearing_reads": marker_reads,
        "is_error": any(bool(event.get("is_error")) for event in events if isinstance(event, dict)),
    }


def new_run_record(arm: str, *, scored: bool) -> dict[str, Any]:
    arm_config(arm)
    return {
        "fixture": "v1",
        "arm": arm,
        "scored": scored,
        "fixture_source_commit": None,
        "target_initial_commit": None,
        "claude_code_version": None,
        "model_id": None,
        "prompt_hashes": None,
        "compact_boundary": None,
        "survival_markers": None,
        "survival_score": None,
        "visible_tests_pass": None,
        "hidden_tests_pass": None,
        "hidden_test_results": None,
        "rehydrate_context_chars": None,
        "hook_errors": None,
        "wall_time_seconds": None,
        "model_id_observed": None,
        "auto_compact_window": None,
        "turn_analyses": [],
        "substantive_turns_after_state": [],
        "marker_bearing_reads_in_final_8": [],
        "context_guard_events": None if not arm_config(arm)["hooks"] else [],
        "compaction_observed": None,
        "aborted_reason": None,
    }


def _stream_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _first_init(events: list[dict]) -> dict[str, Any] | None:
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event
    return None


def _event_text(events: list[dict]) -> str:
    parts: list[str] = []
    for event in events:
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                        parts.append(item["text"])
        result = event.get("result")
        if isinstance(result, str):
            parts.append(result)
    return "\n".join(parts)


def _run_claude(argv: list[str], cwd: Path, env: dict[str, str]) -> tuple[str, list[dict], int | None, str | None]:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=TURN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return output, _stream_events(output), None, f"turn timeout after {TURN_TIMEOUT_SECONDS}s"
    return completed.stdout, _stream_events(completed.stdout), completed.returncode, None


def _claude_argv(prompt: str, model_id: str, *, resume: str | None = None, allowed: tuple[str, ...] | None = None, disallowed: tuple[str, ...] | None = None) -> list[str]:
    argv = [
        "claude",
        "-p",
        prompt,
        "--model",
        model_id,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if resume is not None:
        argv.extend(["--resume", resume])
    if allowed is not None:
        argv.extend(["--allowedTools", *allowed])
    if disallowed is not None:
        argv.extend(["--disallowedTools", *disallowed])
    return argv


def _read_context_guard_events(target: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    root = target / ".claude" / "context-guard" / "sessions"
    if not root.is_dir():
        return events
    for path in sorted(root.glob("*/events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _compaction_observation(events: list[dict], returncode: int | None) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for event in events:
        text = json.dumps(event, ensure_ascii=False).lower()
        if "compact" in text or "compaction" in text:
            evidence.append(event)
    return {
        # Whether the scripted /compact turn itself succeeded. This is NOT a
        # count of how many compactions occurred: an auto-compaction earlier in
        # the run would not show up here. Arms with hooks get the real count
        # from pre_compact events below; A/B stay null rather than guess.
        "scripted_compact_succeeded": None if returncode is None else returncode == 0,
        "pre_compact_events": None,
        "evidence": [{"source": "compact_command", "returncode": returncode}, *evidence],
    }


def _run_evaluators(target: Path) -> tuple[bool | None, bool | None, dict[str, Any] | None]:
    visible = subprocess.run(
        ["python3", "-m", "unittest", "discover", "-s", "tests"],
        cwd=target,
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
        timeout=TURN_TIMEOUT_SECONDS,
    )
    try:
        from .evaluate_hidden import evaluate

        hidden_result = evaluate(target)
        hidden = bool(hidden_result.get("pass"))
        # SPEC 11 wants the individual hidden-test results, not only pass/fail.
        checks = hidden_result.get("checks") if isinstance(hidden_result.get("checks"), dict) else None
    except Exception:
        hidden = None
        checks = None
    return visible.returncode == 0, hidden, checks


def _write_record(path: Path, record: dict[str, Any]) -> None:
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_one_arm(
    arm: str,
    *,
    output_root: Path,
    context_guard_root: Path = REPO_ROOT,
    scored: bool = True,
    keep_target: bool = False,
    run_timestamp: str | None = None,
) -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    prompts = _load_json(PROMPTS_PATH)
    markers = load_markers()
    record = new_run_record(arm, scored=scored)
    hashes = prompt_hashes(prompts)
    record.update(
        {
            "fixture_source_commit": manifest.get("fixture_source_commit") or fixture_source_commit(),
            "claude_code_version": manifest.get("claude_code_version"),
            "model_id": manifest.get("model_id"),
            "prompt_hashes": [
                hashes["initial"],
                *hashes["turns"],
                hashes["probe"],
                hashes["resume"],
            ],
            "compact_boundary": manifest.get("fixed_compact_boundary"),
            "auto_compact_window": AUTO_COMPACT_WINDOW,
        }
    )
    started = time.monotonic()
    output_root = Path(output_root).resolve()
    timestamp = run_timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / timestamp / arm
    run_dir.mkdir(parents=True, exist_ok=True)
    record_path = run_dir / "run.json"
    target: Path | None = None
    temporary_target: tempfile.TemporaryDirectory[str] | None = None
    try:
        leaks = prompt_marker_leaks(prompts, markers)
        if leaks:
            record["aborted_reason"] = "prompt marker leak: " + "; ".join(leaks)
            return record
        if keep_target:
            target = run_dir / "target"
            prepared = prepare_target(arm, target, context_guard_root)
        else:
            temporary_target = tempfile.TemporaryDirectory(prefix=f"fixture-v1-{arm}-")
            target = Path(temporary_target.name)
            prepared = prepare_target(arm, target, context_guard_root)
        expected_commit = manifest.get("target_initial_commit")
        if prepared["initial_commit"] != expected_commit:
            raise ValueError(
                "materialized target commit does not match manifest: "
                f"{prepared['initial_commit']} != {expected_commit}"
            )
        record["target_initial_commit"] = prepared["initial_commit"]
        env = dict(os.environ)
        env.update({
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": AUTO_COMPACT_WINDOW,
            "CLAUDE_PROJECT_DIR": str(target),
        })
        model_id = manifest.get("model_id")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("manifest model_id is not pinned")

        session_id: str | None = None
        for turn_number, prompt in enumerate([prompts["initial"], *prompts["turns"]], start=INITIAL_TURN):
            argv = _claude_argv(
                prompt,
                model_id,
                resume=session_id,
                allowed=WORK_ALLOWED_TOOLS,
            )
            raw, events, returncode, timeout_reason = _run_claude(argv, target, env)
            (run_dir / f"turn-{turn_number:02d}.jsonl").write_text(raw, encoding="utf-8")
            analysis = analyze_turn(events)
            record["turn_analyses"].append({"turn": turn_number, **analysis})
            if is_post_state_turn(turn_number) and (analysis["tool_uses"] > 0 or _event_text(events).strip()):
                record["substantive_turns_after_state"].append(turn_number)
            if is_final_pre_compact_turn(turn_number):
                record["marker_bearing_reads_in_final_8"].append(
                    {"turn": turn_number, "reads": analysis["marker_bearing_reads"]}
                )
            if turn_number == INITIAL_TURN:
                init = _first_init(events)
                observed = init.get("model") if init else None
                record["model_id_observed"] = observed
                if not init:
                    record["aborted_reason"] = "missing system/init event"
                    break
                session_id = init.get("session_id")
                if not isinstance(session_id, str) or not session_id:
                    record["aborted_reason"] = "missing session_id in system/init event"
                    break
                if observed != model_id:
                    record["aborted_reason"] = f"model drift: observed {observed!r}, expected {model_id!r}"
                    break
            if timeout_reason:
                record["aborted_reason"] = timeout_reason
                break
            if returncode != 0:
                record["aborted_reason"] = f"turn {turn_number} exited with status {returncode}"
                break

        if record["aborted_reason"] is None and session_id is not None:
            compact_raw, compact_events, compact_code, compact_timeout = _run_claude(
                _claude_argv("/compact", model_id, resume=session_id), target, env
            )
            (run_dir / "compact.jsonl").write_text(compact_raw, encoding="utf-8")
            record["compaction_observed"] = _compaction_observation(compact_events, compact_code)
            if compact_timeout:
                record["aborted_reason"] = compact_timeout
            elif compact_code != 0:
                record["aborted_reason"] = f"compact exited with status {compact_code}"
            else:
                probe_raw, probe_events, probe_code, probe_timeout = _run_claude(
                    _claude_argv(
                        prompts["probe"],
                        model_id,
                        resume=session_id,
                        disallowed=PROBE_DISALLOWED_TOOLS,
                    ),
                    target,
                    env,
                )
                (run_dir / "probe.jsonl").write_text(probe_raw, encoding="utf-8")
                score = score_text(_event_text(probe_events), markers)
                record["survival_markers"] = score["markers"]
                record["survival_score"] = score["score"]
                if probe_timeout:
                    record["aborted_reason"] = probe_timeout
                elif probe_code != 0:
                    record["aborted_reason"] = f"probe exited with status {probe_code}"
                else:
                    resume_raw, _, resume_code, resume_timeout = _run_claude(
                        _claude_argv(
                            prompts["resume"],
                            model_id,
                            resume=session_id,
                            allowed=WORK_ALLOWED_TOOLS,
                        ),
                        target,
                        env,
                    )
                    (run_dir / "resume.jsonl").write_text(resume_raw, encoding="utf-8")
                    if resume_timeout:
                        record["aborted_reason"] = resume_timeout
                    elif resume_code != 0:
                        record["aborted_reason"] = f"resume exited with status {resume_code}"

        if target is not None:
            visible, hidden, hidden_checks = _run_evaluators(target)
            record["visible_tests_pass"] = visible
            record["hidden_tests_pass"] = hidden
            record["hidden_test_results"] = hidden_checks
            if arm_config(arm)["hooks"]:
                context_events = _read_context_guard_events(target)
                record["context_guard_events"] = context_events
                observation = record.get("compaction_observed")
                if isinstance(observation, dict):
                    observation["pre_compact_events"] = sum(
                        event.get("event") == "pre_compact" for event in context_events
                    )
                if context_events:
                    record["hook_errors"] = sum(
                        event.get("event") == "hook_error" for event in context_events
                    )
                rehydrates = [event.get("context_chars") for event in context_events if event.get("event") == "rehydrate"]
                if rehydrates and all(isinstance(value, int) for value in rehydrates):
                    record["rehydrate_context_chars"] = rehydrates[-1]
    except Exception as error:
        record["aborted_reason"] = f"{type(error).__name__}: {error}"
    finally:
        record["wall_time_seconds"] = round(time.monotonic() - started, 3)
        _write_record(record_path, record)
        if temporary_target is not None:
            temporary_target.cleanup()
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fixture-v1 Claude Code benchmark arms")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--arm", choices=ARMS)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path("benchmarks/runs"))
    parser.add_argument("--keep-target", action="store_true")
    args = parser.parse_args(argv)
    arms = ARMS if args.all else (args.arm,)
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = [
        run_one_arm(
            arm,
            output_root=args.output_root,
            scored=not args.dry_run,
            keep_target=args.keep_target,
            run_timestamp=run_timestamp,
        )
        for arm in arms
    ]
    return 0 if all(result["aborted_reason"] is None for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
