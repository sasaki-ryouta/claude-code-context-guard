"""Contract for the A/B/C/D benchmark runner (docs/benchmark-fixture-v1.md)."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from _support import REPO_ROOT

from benchmarks.fixture_v1 import run_arm
from benchmarks.fixture_v1.score_markers import load_markers

FIXTURE = REPO_ROOT / "benchmarks" / "fixture_v1"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
PROMPTS = json.loads((FIXTURE / "prompts.json").read_text(encoding="utf-8"))


class TestArmDefinitions(unittest.TestCase):
    def test_four_arms_match_the_spec_table(self):
        self.assertEqual(run_arm.ARMS, ("A", "B", "C", "D"))
        expected = {
            "A": {"working_state": False, "hooks": False},
            "B": {"working_state": True, "hooks": False},
            "C": {"working_state": True, "hooks": True},
            "D": {"working_state": False, "hooks": True},
        }
        for arm, want in expected.items():
            with self.subTest(arm=arm):
                config = run_arm.arm_config(arm)
                self.assertEqual(config["working_state"], want["working_state"])
                self.assertEqual(config["hooks"], want["hooks"])

    def test_unknown_arm_is_rejected(self):
        with self.assertRaises(ValueError):
            run_arm.arm_config("E")


class TestTargetPreparation(unittest.TestCase):
    def _prepare(self, arm: str, tmp: str) -> dict:
        return run_arm.prepare_target(arm, Path(tmp) / f"target-{arm}", REPO_ROOT)

    def test_every_arm_starts_from_the_pinned_commit(self):
        # Arm-specific assets must not change the target's initial commit,
        # otherwise provenance cannot compare arms against one pinned tree.
        for arm in run_arm.ARMS:
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                prepared = self._prepare(arm, tmp)
                self.assertEqual(prepared["initial_commit"], MANIFEST["target_initial_commit"])

    def test_arm_a_is_the_bare_native_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(self._prepare("A", tmp)["target"])
            self.assertFalse((target / "CLAUDE.md").exists())
            self.assertFalse((target / ".claude" / "settings.json").exists())
            self.assertFalse((target / ".claude" / "context-guard" / "WORKING_STATE.md").exists())

    def test_arm_b_has_state_without_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(self._prepare("B", tmp)["target"])
            self.assertTrue((target / "CLAUDE.md").exists())
            self.assertTrue((target / ".claude" / "context-guard" / "WORKING_STATE.md").exists())
            self.assertFalse((target / ".claude" / "settings.json").exists())

    def test_arm_d_has_hooks_without_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(self._prepare("D", tmp)["target"])
            self.assertTrue((target / ".claude" / "settings.json").exists())
            self.assertFalse((target / "CLAUDE.md").exists())
            self.assertFalse((target / ".claude" / "context-guard" / "WORKING_STATE.md").exists())

    def test_b_and_c_differ_only_by_hooks(self):
        # SPEC 14: "confirm B/C state handling is identical except hooks".
        with tempfile.TemporaryDirectory() as tmp:
            b = Path(self._prepare("B", tmp)["target"])
            c = Path(self._prepare("C", tmp)["target"])
            for relative in ("CLAUDE.md", ".claude/context-guard/WORKING_STATE.md"):
                with self.subTest(file=relative):
                    self.assertEqual(
                        (b / relative).read_bytes(), (c / relative).read_bytes()
                    )
            self.assertTrue((c / ".claude" / "settings.json").exists())

    def test_arm_c_hooks_point_at_this_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(self._prepare("C", tmp)["target"])
            settings = json.loads((target / ".claude" / "settings.json").read_text(encoding="utf-8"))
            hooks = settings["hooks"]
            self.assertEqual(
                sorted(hooks), ["PostCompact", "PreCompact", "SessionStart"]
            )
            self.assertEqual(hooks["SessionStart"][0]["matcher"], "compact")
            for event in ("PreCompact", "PostCompact"):
                self.assertEqual(hooks[event][0]["matcher"], "manual|auto")
            commands = [
                entry["command"]
                for event in hooks.values()
                for block in event
                for entry in block["hooks"]
            ]
            self.assertEqual(len(commands), 3)
            for command in commands:
                # $CLAUDE_PROJECT_DIR would resolve to the target repo, which
                # has no context_guard package; the path must be absolute.
                self.assertNotIn("CLAUDE_PROJECT_DIR", command)
                self.assertIn(str(REPO_ROOT / "src"), command)

    def test_runtime_state_and_assets_stay_out_of_the_target_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(self._prepare("C", tmp)["target"])
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=target,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertNotIn("WORKING_STATE.md", status)
            self.assertNotIn("settings.json", status)

    def test_hidden_evaluator_is_never_placed_in_the_target(self):
        for arm in run_arm.ARMS:
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                target = Path(self._prepare(arm, tmp)["target"])
                self.assertEqual(list(target.rglob("evaluate_hidden.py")), [])
                self.assertEqual(list(target.rglob("markers.json")), [])
                self.assertEqual(list(target.rglob("prompts.json")), [])


class TestPromptPinning(unittest.TestCase):
    def test_prompt_hashes_are_deterministic_and_cover_every_turn(self):
        first = run_arm.prompt_hashes(PROMPTS)
        self.assertEqual(first, run_arm.prompt_hashes(PROMPTS))
        self.assertEqual(len(PROMPTS["turns"]), 14)
        self.assertEqual(len(first["turns"]), 14)
        for key in ("initial", "probe", "resume"):
            self.assertIn(key, first)
            self.assertRegex(first[key], r"^[0-9a-f]{64}$")

    def test_committed_prompts_contain_no_marker_tokens(self):
        # SPEC 8 rule 3/5: the harness must not hand the tokens back to the model.
        self.assertEqual(run_arm.prompt_marker_leaks(PROMPTS, load_markers()), [])

    def test_marker_leak_detector_actually_detects_a_leak(self):
        poisoned = json.loads(json.dumps(PROMPTS))
        poisoned["turns"][9] = "Remember CGV1-GOAL-7F3A while you work."
        leaks = run_arm.prompt_marker_leaks(poisoned, load_markers())
        self.assertEqual(len(leaks), 1)
        self.assertIn("turns[9]", leaks[0])

    def test_compact_boundary_is_pinned_after_turn_14(self):
        self.assertEqual(MANIFEST["fixed_compact_boundary"], "after_turn_14")
        self.assertEqual(run_arm.COMPACT_AFTER_TURN, 14)


class TestTurnNumbering(unittest.TestCase):
    """The initial orientation prompt is not turn 1 (docs/benchmark-fixture-v1.md 7)."""

    def test_initial_prompt_is_turn_zero(self):
        self.assertEqual(run_arm.INITIAL_TURN, 0)

    def test_post_state_window_is_the_twelve_turns_after_state_is_recorded(self):
        # SPEC 8 rule 1/2: state lands on turn 2, then >= 12 substantive turns.
        window = [n for n in range(0, 16) if run_arm.is_post_state_turn(n)]
        self.assertEqual(window, list(range(3, 15)))
        self.assertEqual(len(window), 12)

    def test_final_pre_compact_window_is_exactly_eight_turns(self):
        # SPEC 8 rule 3/4 is about the final EIGHT pre-compact turns.
        window = [n for n in range(0, 16) if run_arm.is_final_pre_compact_turn(n)]
        self.assertEqual(window, list(range(7, 15)))
        self.assertEqual(len(window), 8)

    def test_windows_never_include_the_orientation_prompt(self):
        self.assertFalse(run_arm.is_post_state_turn(run_arm.INITIAL_TURN))
        self.assertFalse(run_arm.is_final_pre_compact_turn(run_arm.INITIAL_TURN))


class TestFixtureProvenance(unittest.TestCase):
    def test_fixture_source_commit_is_resolved_not_left_null(self):
        # A run record that cannot name the harness commit cannot be reproduced.
        commit = run_arm.fixture_source_commit()
        self.assertRegex(commit, r"^[0-9a-f]{40}$")


class TestProbeIsolation(unittest.TestCase):
    def test_probe_disables_file_repository_and_network_tools(self):
        disallowed = set(run_arm.PROBE_DISALLOWED_TOOLS)
        for tool in ("Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebFetch", "WebSearch", "Task"):
            with self.subTest(tool=tool):
                self.assertIn(tool, disallowed)

    def test_working_tools_exclude_network_access(self):
        allowed = set(run_arm.WORK_ALLOWED_TOOLS)
        self.assertNotIn("WebFetch", allowed)
        self.assertNotIn("WebSearch", allowed)
        for tool in ("Read", "Edit", "Bash"):
            self.assertIn(tool, allowed)


class TestTurnAnalysis(unittest.TestCase):
    def _events(self, tool_uses: list[tuple[str, dict]]) -> list[dict]:
        content = [
            {"type": "tool_use", "id": f"t{i}", "name": name, "input": payload}
            for i, (name, payload) in enumerate(tool_uses)
        ]
        return [
            {"type": "system", "subtype": "init", "model": "claude-sonnet-5"},
            {"type": "assistant", "message": {"model": "claude-sonnet-5", "content": content}},
            {"type": "result", "subtype": "success", "is_error": False},
        ]

    def test_counts_tool_uses_and_records_names(self):
        events = self._events([("Read", {"file_path": "/t/src/routeforge/parse.py"}), ("Bash", {"command": "ls"})])
        analysis = run_arm.analyze_turn(events)
        self.assertEqual(analysis["tool_uses"], 2)
        self.assertEqual(sorted(analysis["tools"]), ["Bash", "Read"])
        self.assertFalse(analysis["is_error"])

    def test_flags_reads_of_marker_bearing_material(self):
        # SPEC 8 rule 4: a run that rereads these in the final 8 turns is
        # excluded from the long-distance survival comparison.
        for path in (
            "/t/docs/contract.md",
            "/t/docs/incident.md",
            "/t/.claude/context-guard/WORKING_STATE.md",
        ):
            with self.subTest(path=path):
                analysis = run_arm.analyze_turn(self._events([("Read", {"file_path": path})]))
                self.assertTrue(analysis["marker_bearing_reads"])

    def test_ordinary_source_reads_are_not_flagged(self):
        analysis = run_arm.analyze_turn(self._events([("Read", {"file_path": "/t/src/routeforge/route.py"})]))
        self.assertEqual(analysis["marker_bearing_reads"], [])

    def test_detects_marker_bearing_material_read_through_bash(self):
        analysis = run_arm.analyze_turn(self._events([("Bash", {"command": "cat docs/contract.md"})]))
        self.assertTrue(analysis["marker_bearing_reads"])

    def test_turn_with_no_tool_use_is_reported_as_such(self):
        analysis = run_arm.analyze_turn(self._events([]))
        self.assertEqual(analysis["tool_uses"], 0)


class TestRunRecord(unittest.TestCase):
    def test_record_skeleton_covers_every_required_provenance_field(self):
        record = run_arm.new_run_record("C", scored=False)
        for field in (
            "fixture",
            "arm",
            "scored",
            "fixture_source_commit",
            "target_initial_commit",
            "claude_code_version",
            "model_id",
            "prompt_hashes",
            "compact_boundary",
            "survival_markers",
            "survival_score",
            "visible_tests_pass",
            "hidden_tests_pass",
            "rehydrate_context_chars",
            "hook_errors",
            "wall_time_seconds",
        ):
            with self.subTest(field=field):
                self.assertIn(field, record)

    def test_dry_run_records_are_explicitly_unscored(self):
        self.assertFalse(run_arm.new_run_record("A", scored=False)["scored"])

    def test_unavailable_metrics_are_null_not_guessed(self):
        record = run_arm.new_run_record("A", scored=False)
        self.assertIsNone(record["survival_score"])
        self.assertIsNone(record["visible_tests_pass"])
        self.assertIsNone(record["hidden_tests_pass"])
        self.assertIsNone(record["rehydrate_context_chars"])


if __name__ == "__main__":
    unittest.main()
