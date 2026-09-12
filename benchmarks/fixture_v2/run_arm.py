from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.fixture_v1 import run_arm as core

from .materialize import materialize
from .score_markers import load_markers, score_text


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
MANIFEST_PATH = HERE / "manifest.json"
PROMPTS_PATH = HERE / "prompts.json"
COMPACT_AFTER_TURN = 14
INITIAL_TURN = 0
STATE_RECORDED_TURN = 2
FINAL_PRE_COMPACT_TURNS = 8
DISABLE_AUTO_COMPACT = "1"
DISABLE_AUTOUPDATER = "1"
ARMS = core.ARMS
WORK_ALLOWED_TOOLS = core.WORK_ALLOWED_TOOLS
PROBE_DISALLOWED_TOOLS = core.PROBE_DISALLOWED_TOOLS
TURN_TIMEOUT_SECONDS = core.TURN_TIMEOUT_SECONDS


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def is_post_state_turn(turn_number: int) -> bool:
    return STATE_RECORDED_TURN < turn_number <= COMPACT_AFTER_TURN


def is_final_pre_compact_turn(turn_number: int) -> bool:
    first = COMPACT_AFTER_TURN - FINAL_PRE_COMPACT_TURNS + 1
    return first <= turn_number <= COMPACT_AFTER_TURN


def fixture_source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()


def tracked_dirty_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def observed_claude_version() -> str:
    completed = subprocess.run(
        ["claude", "--version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        env={**os.environ, "DISABLE_AUTOUPDATER": DISABLE_AUTOUPDATER},
    )
    return (completed.stdout or completed.stderr).strip()


def version_matches(observed: str, expected: str) -> bool:
    return observed.split(maxsplit=1)[0] == expected


def prepare_target(arm: str, destination: Path, context_guard_root: Path) -> dict[str, Any]:
    config = core.arm_config(arm)
    target = Path(destination).resolve()
    initial_commit = materialize(target)
    assets = HERE / "arm_assets"

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
            json.dumps(core._settings(Path(context_guard_root)), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return {"target": target, "initial_commit": initial_commit, "arm": arm, **config}


def compact_boundaries(events: list[dict]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("type") == "system"
        and event.get("subtype") == "compact_boundary"
    ]


def marker_echoes(events: list[dict], markers: dict[str, str]) -> list[str]:
    text = core._event_text(events)
    return [name for name, token in markers.items() if token in text]


def state_marker_presence(target: Path, markers: dict[str, str]) -> dict[str, bool] | None:
    state = target / ".claude" / "context-guard" / "WORKING_STATE.md"
    if not state.is_file():
        return None
    text = state.read_text(encoding="utf-8")
    return {name: token in text for name, token in markers.items()}


def new_run_record(arm: str, *, scored: bool) -> dict[str, Any]:
    record = core.new_run_record(arm, scored=scored)
    record.update(
        {
            "fixture": "v2",
            "claude_code_version_observed_start": None,
            "claude_code_version_observed_end": None,
            "fixture_source_dirty": None,
            "auto_compaction_control": "DISABLE_AUTO_COMPACT=1",
            "auto_updater_control": "DISABLE_AUTOUPDATER=1",
            "pre_boundary_compact_boundaries": [],
            "compact_boundary_events": [],
            "marker_echoes_in_final_8": [],
            "state_markers_before_compact": None,
            "initial_tool_uses": None,
            "long_distance_valid": None,
        }
    )
    record.pop("auto_compact_window", None)
    return record


def _write_record(path: Path, record: dict[str, Any]) -> None:
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _validity(record: dict[str, Any]) -> bool:
    substantive = record.get("substantive_turns_after_state") or []
    reads = record.get("marker_bearing_reads_in_final_8") or []
    echoes = record.get("marker_echoes_in_final_8") or []
    return (
        len(substantive) >= 12
        and not any(item.get("reads") for item in reads if isinstance(item, dict))
        and not any(item.get("markers") for item in echoes if isinstance(item, dict))
        and not record.get("pre_boundary_compact_boundaries")
        and len(record.get("compact_boundary_events") or []) == 1
        and record.get("initial_tool_uses") == 0
    )


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
    core.arm_config(arm)
    record = new_run_record(arm, scored=scored)
    hashes = core.prompt_hashes(prompts)
    record.update(
        {
            "fixture_source_commit": fixture_source_commit(),
            "claude_code_version": manifest.get("claude_code_version"),
            "model_id": manifest.get("model_id"),
            "prompt_hashes": [hashes["initial"], *hashes["turns"], hashes["probe"], hashes["resume"]],
            "compact_boundary": manifest.get("fixed_compact_boundary"),
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
        dirty = tracked_dirty_paths()
        record["fixture_source_dirty"] = dirty
        if dirty:
            record["aborted_reason"] = "fixture source has tracked modifications: " + "; ".join(dirty)
            return record

        observed_version = observed_claude_version()
        record["claude_code_version_observed_start"] = observed_version
        expected_version = manifest.get("claude_code_version")
        if not isinstance(expected_version, str) or not version_matches(observed_version, expected_version):
            record["aborted_reason"] = f"Claude Code version drift: observed {observed_version!r}, expected {expected_version!r}"
            return record

        leaks = core.prompt_marker_leaks(prompts, markers)
        if leaks:
            record["aborted_reason"] = "prompt marker leak: " + "; ".join(leaks)
            return record

        if keep_target:
            target = run_dir / "target"
            prepared = prepare_target(arm, target, context_guard_root)
        else:
            temporary_target = tempfile.TemporaryDirectory(prefix=f"fixture-v2-{arm}-")
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
        env.pop("CLAUDE_CODE_AUTO_COMPACT_WINDOW", None)
        env.update(
            {
                "DISABLE_AUTO_COMPACT": DISABLE_AUTO_COMPACT,
                "DISABLE_AUTOUPDATER": DISABLE_AUTOUPDATER,
                "CLAUDE_PROJECT_DIR": str(target),
            }
        )

        model_id = manifest.get("model_id")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("manifest model_id is not pinned")

        session_id: str | None = None
        scripted = [prompts["initial"], *prompts["turns"]]
        for turn_number, prompt in enumerate(scripted, start=INITIAL_TURN):
            if turn_number == INITIAL_TURN:
                argv = core._claude_argv(prompt, model_id, resume=None, disallowed=PROBE_DISALLOWED_TOOLS)
            else:
                argv = core._claude_argv(prompt, model_id, resume=session_id, allowed=WORK_ALLOWED_TOOLS)
            raw, events, returncode, timeout_reason = core._run_claude(argv, target, env)
            (run_dir / f"turn-{turn_number:02d}.jsonl").write_text(raw, encoding="utf-8")

            analysis = core.analyze_turn(events)
            record["turn_analyses"].append({"turn": turn_number, **analysis})
            boundaries = compact_boundaries(events)
            if boundaries:
                record["pre_boundary_compact_boundaries"].extend(
                    {"turn": turn_number, "event": event} for event in boundaries
                )
            if is_post_state_turn(turn_number) and (analysis["tool_uses"] > 0 or core._event_text(events).strip()):
                record["substantive_turns_after_state"].append(turn_number)
            if is_final_pre_compact_turn(turn_number):
                record["marker_bearing_reads_in_final_8"].append(
                    {"turn": turn_number, "reads": analysis["marker_bearing_reads"]}
                )
                record["marker_echoes_in_final_8"].append(
                    {"turn": turn_number, "markers": marker_echoes(events, markers)}
                )

            if turn_number == INITIAL_TURN:
                record["initial_tool_uses"] = analysis["tool_uses"]
                init = core._first_init(events)
                observed_model = init.get("model") if init else None
                record["model_id_observed"] = observed_model
                if not init:
                    record["aborted_reason"] = "missing system/init event"
                    break
                session_id = init.get("session_id")
                if not isinstance(session_id, str) or not session_id:
                    record["aborted_reason"] = "missing session_id in system/init event"
                    break
                if observed_model != model_id:
                    record["aborted_reason"] = f"model drift: observed {observed_model!r}, expected {model_id!r}"
                    break

            if timeout_reason:
                record["aborted_reason"] = timeout_reason
                break
            if returncode != 0:
                record["aborted_reason"] = f"turn {turn_number} exited with status {returncode}"
                break
            if boundaries:
                record["aborted_reason"] = f"unexpected compaction before fixed boundary at turn {turn_number}"
                break

        if target is not None:
            record["state_markers_before_compact"] = state_marker_presence(target, markers)

        compact_events: list[dict] = []
        probe_events: list[dict] = []
        if record["aborted_reason"] is None and session_id is not None:
            compact_raw, compact_events, compact_code, compact_timeout = core._run_claude(
                core._claude_argv("/compact", model_id, resume=session_id), target, env
            )
            (run_dir / "compact.jsonl").write_text(compact_raw, encoding="utf-8")
            record["compaction_observed"] = {
                "scripted_compact_succeeded": None if compact_code is None else compact_code == 0,
                "pre_compact_events": None,
            }
            if compact_timeout:
                record["aborted_reason"] = compact_timeout
            elif compact_code != 0:
                record["aborted_reason"] = f"compact exited with status {compact_code}"
            else:
                probe_raw, probe_events, probe_code, probe_timeout = core._run_claude(
                    core._claude_argv(
                        prompts["probe"], model_id, resume=session_id, disallowed=PROBE_DISALLOWED_TOOLS
                    ),
                    target,
                    env,
                )
                (run_dir / "probe.jsonl").write_text(probe_raw, encoding="utf-8")
                score = score_text(core._event_text(probe_events), markers)
                record["survival_markers"] = score["markers"]
                record["survival_score"] = score["score"]
                record["compact_boundary_events"] = [
                    *compact_boundaries(compact_events),
                    *compact_boundaries(probe_events),
                ]
                if probe_timeout:
                    record["aborted_reason"] = probe_timeout
                elif probe_code != 0:
                    record["aborted_reason"] = f"probe exited with status {probe_code}"
                elif len(record["compact_boundary_events"]) != 1:
                    record["aborted_reason"] = (
                        "expected exactly one compact_boundary event around scripted /compact, observed "
                        + str(len(record["compact_boundary_events"]))
                    )
                else:
                    resume_raw, _, resume_code, resume_timeout = core._run_claude(
                        core._claude_argv(
                            prompts["resume"], model_id, resume=session_id, allowed=WORK_ALLOWED_TOOLS
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
            visible, hidden, hidden_checks = core._run_evaluators(target)
            record["visible_tests_pass"] = visible
            record["hidden_tests_pass"] = hidden
            record["hidden_test_results"] = hidden_checks
            if core.arm_config(arm)["hooks"]:
                context_events = core._read_context_guard_events(target)
                record["context_guard_events"] = context_events
                observation = record.get("compaction_observed")
                if isinstance(observation, dict):
                    observation["pre_compact_events"] = sum(
                        event.get("event") == "pre_compact" for event in context_events
                    )
                record["hook_errors"] = sum(event.get("event") == "hook_error" for event in context_events)
                rehydrates = [
                    event.get("context_chars")
                    for event in context_events
                    if event.get("event") == "rehydrate"
                ]
                if rehydrates and all(isinstance(value, int) for value in rehydrates):
                    record["rehydrate_context_chars"] = rehydrates[-1]

        observed_end = observed_claude_version()
        record["claude_code_version_observed_end"] = observed_end
        if record["aborted_reason"] is None and observed_end != record["claude_code_version_observed_start"]:
            record["aborted_reason"] = "Claude Code version changed during run"

        record["long_distance_valid"] = _validity(record)
    except Exception as error:
        record["aborted_reason"] = f"{type(error).__name__}: {error}"
    finally:
        record["wall_time_seconds"] = round(time.monotonic() - started, 3)
        _write_record(record_path, record)
        if temporary_target is not None:
            temporary_target.cleanup()
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fixture-v2 Claude Code benchmark arms")
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
