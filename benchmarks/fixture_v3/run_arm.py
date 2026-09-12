from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.fixture_v1 import run_arm as core
from benchmarks.fixture_v2 import run_arm as v2

from .materialize import materialize
from .score_markers import load_markers, score_text


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
MANIFEST_PATH = HERE / "manifest.json"
PROMPTS_PATH = HERE / "prompts.json"
SEMANTIC_ANSWERS_PATH = HERE / "semantic_answers.json"
COMPACT_AFTER_TURN = 14
INITIAL_TURN = 0
STATE_RECORDED_TURN = 2
FINAL_PRE_COMPACT_TURNS = 8
DISABLE_AUTO_COMPACT = "1"
DISABLE_AUTOUPDATER = "1"
# Claude Code Auto Memory is on by default and loads per-repository memory at
# session start. That is a second persistent-memory channel and would confound
# a memory experiment, so every arm disables it.
DISABLE_AUTO_MEMORY = "1"
# Host user settings load plugins, hooks, skills and MCP servers into every
# `claude -p`. In the pre-control diagnostic run a host SessionStart plugin hook
# injected the PREVIOUS arm's session summary into the next arm's first turn, so
# restricting setting sources is a validity control, not hygiene. "project" is a
# documented --setting-sources value and, unlike --bare, leaves auth untouched.
SETTING_SOURCES = "project"
# `.claude/` is a built-in sensitive path. With host settings excluded the
# model's WORKING_STATE write is denied, which silently removes the behaviour
# arms B/C exist to test. "auto" restores the same permission posture the host
# previously supplied via defaultMode, but declares it explicitly so the run no
# longer depends on host configuration. It is applied identically to every arm,
# and is deliberately not bypassPermissions.
PERMISSION_MODE = "auto"
# Hooks the fixture itself installs through inline --settings for C/D.
EXPECTED_HOOK_PREFIXES = ("PreCompact", "PostCompact", "SessionStart")


def benchmark_env(target: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment shared by every Claude invocation in a run.

    Built in one place so no invocation can quietly run without the controls;
    a test asserts that each `_run_claude` call is handed this same mapping.
    """
    env = dict(os.environ if base is None else base)
    env.pop("CLAUDE_CODE_AUTO_COMPACT_WINDOW", None)
    env.update(
        {
            "DISABLE_AUTO_COMPACT": DISABLE_AUTO_COMPACT,
            "DISABLE_AUTOUPDATER": DISABLE_AUTOUPDATER,
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": DISABLE_AUTO_MEMORY,
            "CLAUDE_PROJECT_DIR": str(target),
        }
    )
    return env


def host_config_provenance() -> dict[str, Any]:
    """Identify host configuration that `claude -p` can still discover.

    Without --bare, working-directory and ~/.claude configuration remain
    visible. Record presence, size, and digest only - never the contents,
    which can hold credentials.
    """
    home = Path.home() / ".claude"
    candidates = {
        "user_settings": home / "settings.json",
        "user_memory": home / "CLAUDE.md",
        "user_claude_json": Path.home() / ".claude.json",
    }
    provenance: dict[str, Any] = {}
    for name, path in candidates.items():
        try:
            if path.is_file():
                data = path.read_bytes()
                provenance[name] = {
                    "present": True,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            else:
                provenance[name] = {"present": False, "bytes": None, "sha256": None}
        except OSError:
            provenance[name] = {"present": None, "bytes": None, "sha256": None}
    return provenance
ARMS = core.ARMS
WORK_ALLOWED_TOOLS = core.WORK_ALLOWED_TOOLS
# Denylisting cannot be complete - TaskOutput retrieves persisted task output,
# and new tools arrive with new Claude Code releases - so this list is a first
# line of defence only. The enforced invariant is behavioural: a probe that used
# any tool at all invalidates the run (see _validity).
PROBE_DISALLOWED_TOOLS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *core.PROBE_DISALLOWED_TOOLS,
            "TaskOutput",
            "TaskStop",
            "NotebookEdit",
            "TodoWrite",
            "SlashCommand",
            "ListMcpResourcesTool",
            "ReadMcpResourceTool",
        )
    )
)
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
    return v2.fixture_source_commit()


def tracked_dirty_paths() -> list[str]:
    return v2.tracked_dirty_paths()


def observed_claude_version() -> str:
    return v2.observed_claude_version()


def version_matches(observed: str, expected: str) -> bool:
    return v2.version_matches(observed, expected)


def prepare_target(arm: str, destination: Path, context_guard_root: Path) -> dict[str, Any]:
    """Materialize only arm-visible state assets; hook settings stay outside target."""
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

    return {"target": target, "initial_commit": initial_commit, "arm": arm, **config}


def hook_settings_json(arm: str, context_guard_root: Path) -> str | None:
    if not core.arm_config(arm)["hooks"]:
        return None
    return json.dumps(
        core._settings(Path(context_guard_root)),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def claude_argv(
    prompt: str,
    model_id: str,
    *,
    settings_json: str | None,
    resume: str | None = None,
    allowed: tuple[str, ...] | None = None,
    disallowed: tuple[str, ...] | None = None,
) -> list[str]:
    argv = core._claude_argv(
        prompt,
        model_id,
        resume=resume,
        allowed=allowed,
        disallowed=disallowed,
    )
    argv.extend(["--setting-sources", SETTING_SOURCES, "--permission-mode", PERMISSION_MODE])
    if settings_json is not None:
        argv.extend(["--settings", settings_json])
    return argv


def host_surface(events: list[dict]) -> dict[str, int]:
    """Plugins/skills/MCP servers the session actually loaded, from system/init."""
    surface = {"plugins": 0, "skills": 0, "mcp_servers": 0}
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            for key in surface:
                value = event.get(key)
                surface[key] = len(value) if isinstance(value, list) else 0
            break
    return surface


def foreign_hooks(events: list[dict], *, arm: str) -> list[str]:
    """Hook executions that this fixture did not install.

    Arms A and B install no hooks, so any execution is foreign. Arms C and D
    install the three Context Guard hooks, so only other names are foreign.
    """
    expected = EXPECTED_HOOK_PREFIXES if core.arm_config(arm)["hooks"] else ()
    names: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "hook_started":
            name = event.get("hook_name")
            if not isinstance(name, str):
                continue
            if not name.startswith(expected) if expected else True:
                names.append(name)
    return names


def compact_boundaries(events: list[dict]) -> list[dict[str, Any]]:
    return v2.compact_boundaries(events)


def marker_echoes(events: list[dict], markers: dict[str, str]) -> list[str]:
    """Canaries appearing anywhere in a turn, including tool results.

    Assistant prose alone is not enough: a Grep that returns a canary puts it
    back in context just as effectively as saying it, so the whole event stream
    for the turn is searched.
    """
    try:
        blob = json.dumps(events, ensure_ascii=False)
    except (TypeError, ValueError):
        blob = str(events)
    return [name for name, token in markers.items() if token in blob]


# Every document that carries canaries or the durable facts behind them.
# Declared once: a second list is how contract.md ended up covered while
# incident.md did not.
MARKER_MATERIAL_FILENAMES: tuple[str, ...] = (
    "contract.md",
    "incident.md",
    "recall-tags.md",
    "WORKING_STATE.md",
)


def _probe_material(value: str) -> bool:
    # Match on bare filenames. Two earlier gaps came from qualifying the
    # needles: an anchored endswith() missed a serialized input, and path
    # prefixes missed `cd docs && cat contract.md`. A basename cannot be
    # sidestepped by changing directory first, and these names are specific
    # enough that an ordinary task reference to them is itself a reread.
    normalized = value.replace("\\", "/")
    return any(needle in normalized for needle in MARKER_MATERIAL_FILENAMES)


def probe_material_reads(events: list[dict]) -> list[str]:
    """Any tool call that names marker-bearing material, whatever the tool.

    Inspecting only Read.file_path and Bash.command missed Grep and Glob, and
    would miss every tool added in a future release. The whole tool input is
    searched instead, so distance is judged on what was touched rather than on
    which tool touched it.
    """
    reads: list[str] = []
    for name, payload in core._tool_uses(events):
        try:
            serialized = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError):
            serialized = str(payload)
        if _probe_material(serialized):
            reads.append(f"{name}: {serialized[:200]}")
    return reads


def state_snapshot(target: Path, markers: dict[str, str]) -> dict[str, Any]:
    path = target / ".claude" / "context-guard" / "WORKING_STATE.md"
    if not path.is_file():
        return {"exists": False, "markers": None, "chars": 0}
    text = path.read_text(encoding="utf-8")
    return {
        "exists": True,
        "markers": {name: token in text for name, token in markers.items()},
        "chars": len(text),
    }


def state_manipulation_valid(arm: str, snapshot: dict[str, Any]) -> bool:
    if arm in ("B", "C"):
        markers = snapshot.get("markers")
        return bool(snapshot.get("exists")) and isinstance(markers, dict) and all(markers.values())
    return not bool(snapshot.get("exists"))


def prompt_canary_leaks(prompts: dict[str, Any], markers: dict[str, str]) -> list[str]:
    leaks: list[str] = []
    values: list[tuple[str, object]] = [("initial", prompts.get("initial"))]
    values.extend((f"turns[{i}]", value) for i, value in enumerate(prompts.get("turns", [])))
    values.extend(
        [
            ("probe", prompts.get("probe")),
            ("semantic_probe", prompts.get("semantic_probe")),
            ("resume", prompts.get("resume")),
        ]
    )
    for label, value in values:
        if not isinstance(value, str):
            continue
        for token in markers.values():
            if token in value:
                leaks.append(f"{label}: {token}")
    return leaks


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_semantic_answers() -> dict[str, str]:
    data = _load_json(SEMANTIC_ANSWERS_PATH)
    answers = data.get("answers")
    if not isinstance(answers, dict) or not answers:
        raise ValueError("semantic_answers.json must contain answers")
    result: dict[str, str] = {}
    for key, value in answers.items():
        if not isinstance(key, str) or not isinstance(value, str) or value not in {"A", "B", "C"}:
            raise ValueError("semantic answer keys must map strings to A/B/C")
        result[key] = value
    return result


def score_semantic(text: str, answers: dict[str, str] | None = None) -> dict[str, Any]:
    key = answers or load_semantic_answers()
    found: dict[str, list[str]] = {name: [] for name in key}
    pattern = re.compile(r"(?mi)^\s*(Q\d+)\s*=\s*([ABC])\s*$")
    for question, answer in pattern.findall(text):
        if question in found:
            found[question].append(answer)
    response = {
        question: values[0] if len(values) == 1 else None
        for question, values in found.items()
    }
    correct = {
        question: response[question] == expected
        for question, expected in key.items()
    }
    hits = sum(correct.values())
    total = len(correct)
    return {
        "answers": response,
        "correct": correct,
        "hits": hits,
        "total": total,
        "score": hits / total if total else 0.0,
    }


def new_run_record(arm: str, *, scored: bool) -> dict[str, Any]:
    record = core.new_run_record(arm, scored=scored)
    record.update(
        {
            "fixture": "v3",
            "claude_code_version_observed_start": None,
            "claude_code_version_observed_end": None,
            "fixture_source_dirty": None,
            "auto_compaction_control": "DISABLE_AUTO_COMPACT=1",
            "auto_updater_control": "DISABLE_AUTOUPDATER=1",
            "auto_memory_control": "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1",
            "setting_sources_control": SETTING_SOURCES,
            "permission_mode_control": PERMISSION_MODE,
            "probe_tool_uses": None,
            "semantic_probe_tool_uses": None,
            "host_surface_observed": None,
            "unexpected_hooks": [],
            "host_config": None,
            "hook_settings_delivery": "inline --settings" if core.arm_config(arm)["hooks"] else None,
            "target_settings_present": None,
            "pre_boundary_compact_boundaries": [],
            "compact_boundary_events": [],
            "marker_echoes_in_final_8": [],
            "state_file_present_before_compact": None,
            "state_markers_before_compact": None,
            "state_chars_before_compact": None,
            "state_manipulation_valid": None,
            "initial_tool_uses": None,
            "semantic_probe": None,
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
    arm = record.get("arm")
    hooks_ok = True
    if arm in ("C", "D"):
        context_chars = record.get("rehydrate_context_chars")
        hooks_ok = (
            record.get("hook_errors") == 0
            and isinstance(context_chars, int)
            and context_chars <= 9000
        )
    surface = record.get("host_surface_observed")
    # Claude Code's own bundled skills load in every arm; only host-supplied
    # plugins and MCP servers indicate that user settings leaked in.
    surface_clean = isinstance(surface, dict) and all(
        surface.get(key) == 0 for key in ("plugins", "mcp_servers")
    )
    # A probe that reached for a tool may have retrieved the answer instead of
    # remembering it, so survival would no longer measure what it claims.
    probes_clean = (
        record.get("probe_tool_uses") == 0 and record.get("semantic_probe_tool_uses") == 0
    )
    controls_ok = (
        probes_clean
        and record.get("auto_memory_control") == "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1"
        and record.get("setting_sources_control") == SETTING_SOURCES
        and surface_clean
        and not record.get("unexpected_hooks")
    )
    return (
        controls_ok
        and len(substantive) >= 12
        and not any(item.get("reads") for item in reads if isinstance(item, dict))
        and not any(item.get("markers") for item in echoes if isinstance(item, dict))
        and not record.get("pre_boundary_compact_boundaries")
        and len(record.get("compact_boundary_events") or []) == 1
        and record.get("initial_tool_uses") == 0
        and record.get("state_manipulation_valid") is True
        and record.get("target_settings_present") is False
        and hooks_ok
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
            "prompt_hashes": [
                hashes["initial"],
                *hashes["turns"],
                hashes["probe"],
                _prompt_hash(prompts["semantic_probe"]),
                hashes["resume"],
            ],
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

        leaks = prompt_canary_leaks(prompts, markers)
        if leaks:
            record["aborted_reason"] = "prompt canary leak: " + "; ".join(leaks)
            return record

        if keep_target:
            target = run_dir / "target"
            prepared = prepare_target(arm, target, context_guard_root)
        else:
            temporary_target = tempfile.TemporaryDirectory(prefix=f"fixture-v3-{arm}-")
            target = Path(temporary_target.name)
            prepared = prepare_target(arm, target, context_guard_root)

        expected_commit = manifest.get("target_initial_commit")
        if prepared["initial_commit"] != expected_commit:
            raise ValueError(
                "materialized target commit does not match manifest: "
                f"{prepared['initial_commit']} != {expected_commit}"
            )
        record["target_initial_commit"] = prepared["initial_commit"]
        record["target_settings_present"] = (target / ".claude" / "settings.json").exists()
        if record["target_settings_present"]:
            raise ValueError("target unexpectedly contains .claude/settings.json")

        settings_json = hook_settings_json(arm, context_guard_root)
        env = benchmark_env(target)
        record["host_config"] = host_config_provenance()

        model_id = manifest.get("model_id")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("manifest model_id is not pinned")

        session_id: str | None = None
        scripted = [prompts["initial"], *prompts["turns"]]
        for turn_number, prompt in enumerate(scripted, start=INITIAL_TURN):
            if turn_number == INITIAL_TURN:
                argv = claude_argv(
                    prompt,
                    model_id,
                    settings_json=settings_json,
                    resume=None,
                    disallowed=PROBE_DISALLOWED_TOOLS,
                )
            else:
                argv = claude_argv(
                    prompt,
                    model_id,
                    settings_json=settings_json,
                    resume=session_id,
                    allowed=WORK_ALLOWED_TOOLS,
                )
            raw, events, returncode, timeout_reason = core._run_claude(argv, target, env)
            (run_dir / f"turn-{turn_number:02d}.jsonl").write_text(raw, encoding="utf-8")

            analysis = core.analyze_turn(events)
            analysis["marker_bearing_reads"] = probe_material_reads(events)
            record["turn_analyses"].append({"turn": turn_number, **analysis})
            record["unexpected_hooks"].extend(foreign_hooks(events, arm=arm))
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
                record["host_surface_observed"] = host_surface(events)
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
            snapshot = state_snapshot(target, markers)
            record["state_file_present_before_compact"] = snapshot["exists"]
            record["state_markers_before_compact"] = snapshot["markers"]
            record["state_chars_before_compact"] = snapshot["chars"]
            record["state_manipulation_valid"] = state_manipulation_valid(arm, snapshot)

        compact_events: list[dict] = []
        probe_events: list[dict] = []
        semantic_events: list[dict] = []
        if record["aborted_reason"] is None and session_id is not None:
            compact_raw, compact_events, compact_code, compact_timeout = core._run_claude(
                claude_argv(
                    "/compact",
                    model_id,
                    settings_json=settings_json,
                    resume=session_id,
                ),
                target,
                env,
            )
            (run_dir / "compact.jsonl").write_text(compact_raw, encoding="utf-8")
            record["unexpected_hooks"].extend(foreign_hooks(compact_events, arm=arm))
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
                    claude_argv(
                        prompts["probe"],
                        model_id,
                        settings_json=settings_json,
                        resume=session_id,
                        disallowed=PROBE_DISALLOWED_TOOLS,
                    ),
                    target,
                    env,
                )
                (run_dir / "probe.jsonl").write_text(probe_raw, encoding="utf-8")
                record["unexpected_hooks"].extend(foreign_hooks(probe_events, arm=arm))
                record["probe_tool_uses"] = core.analyze_turn(probe_events)["tool_uses"]
                score = score_text(core._event_text(probe_events), markers)
                record["survival_markers"] = score["markers"]
                record["survival_score"] = score["score"]
                if probe_timeout:
                    record["aborted_reason"] = probe_timeout
                elif probe_code != 0:
                    record["aborted_reason"] = f"probe exited with status {probe_code}"
                else:
                    semantic_raw, semantic_events, semantic_code, semantic_timeout = core._run_claude(
                        claude_argv(
                            prompts["semantic_probe"],
                            model_id,
                            settings_json=settings_json,
                            resume=session_id,
                            disallowed=PROBE_DISALLOWED_TOOLS,
                        ),
                        target,
                        env,
                    )
                    (run_dir / "semantic-probe.jsonl").write_text(semantic_raw, encoding="utf-8")
                    record["unexpected_hooks"].extend(foreign_hooks(semantic_events, arm=arm))
                    record["semantic_probe_tool_uses"] = core.analyze_turn(semantic_events)["tool_uses"]
                    record["semantic_probe"] = score_semantic(core._event_text(semantic_events))
                    if semantic_timeout:
                        record["aborted_reason"] = semantic_timeout
                    elif semantic_code != 0:
                        record["aborted_reason"] = f"semantic probe exited with status {semantic_code}"

                record["compact_boundary_events"] = [
                    *compact_boundaries(compact_events),
                    *compact_boundaries(probe_events),
                    *compact_boundaries(semantic_events),
                ]
                if record["aborted_reason"] is None and len(record["compact_boundary_events"]) != 1:
                    record["aborted_reason"] = (
                        "expected exactly one compact_boundary event around scripted /compact, observed "
                        + str(len(record["compact_boundary_events"]))
                    )

                if record["aborted_reason"] is None:
                    resume_raw, _, resume_code, resume_timeout = core._run_claude(
                        claude_argv(
                            prompts["resume"],
                            model_id,
                            settings_json=settings_json,
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
    parser = argparse.ArgumentParser(description="Run fixture-v3 Claude Code benchmark arms")
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
