from __future__ import annotations

import json
import ast
import tempfile
import unittest
from pathlib import Path

from _support import REPO_ROOT
from benchmarks.fixture_v3 import run_arm
from benchmarks.fixture_v3.materialize import materialize
from benchmarks.fixture_v3.score_markers import load_markers


FIXTURE = REPO_ROOT / "benchmarks" / "fixture_v3"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
PROMPTS = json.loads((FIXTURE / "prompts.json").read_text(encoding="utf-8"))


class TestNativeMemoryContamination(unittest.TestCase):
    """Auto Memory is a second persistent-memory channel and would confound H1."""

    def _env(self) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            return run_arm.benchmark_env(Path(tmp))

    def test_native_auto_memory_is_disabled(self):
        self.assertEqual(self._env()["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")

    def test_existing_controls_are_retained(self):
        env = self._env()
        self.assertEqual(env["DISABLE_AUTO_COMPACT"], "1")
        self.assertEqual(env["DISABLE_AUTOUPDATER"], "1")

    def test_undocumented_window_control_is_removed(self):
        # v2 relied on an undocumented key; v3 must not inherit it from the host.
        import os

        original = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW")
        os.environ["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = "1000000"
        try:
            self.assertNotIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW", self._env())
        finally:
            if original is None:
                os.environ.pop("CLAUDE_CODE_AUTO_COMPACT_WINDOW", None)
            else:
                os.environ["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = original

    def test_host_cannot_re_enable_auto_memory(self):
        import os

        original = os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY")
        os.environ["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "0"
        try:
            self.assertEqual(self._env()["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
        finally:
            if original is None:
                os.environ.pop("CLAUDE_CODE_DISABLE_AUTO_MEMORY", None)
            else:
                os.environ["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = original

    def test_every_claude_invocation_receives_the_controlled_environment(self):
        # The control is only real if no invocation builds its own environment.
        source = (
            Path(run_arm.__file__).read_text(encoding="utf-8")
        )
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_run_claude"
        ]
        self.assertGreaterEqual(len(calls), 4, "expected the scripted turns, compact, and probes")
        for call in calls:
            env_arg = call.args[2] if len(call.args) >= 3 else None
            self.assertIsInstance(env_arg, ast.Name, ast.unparse(call))
            self.assertEqual(env_arg.id, "env", ast.unparse(call))

    def test_provenance_records_the_control(self):
        record = run_arm.new_run_record("C", scored=False)
        self.assertIn("auto_memory_control", record)
        self.assertEqual(record["auto_memory_control"], "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1")

    def test_provenance_records_host_configuration_surface(self):
        # Without --bare, claude -p can still discover host configuration;
        # record enough to spot drift between runs.
        provenance = run_arm.host_config_provenance()
        self.assertIsInstance(provenance, dict)
        for key in ("user_settings", "user_memory", "user_claude_json"):
            self.assertIn(key, provenance)
            entry = provenance[key]
            self.assertIn("present", entry)
            if entry["present"]:
                self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_host_provenance_never_stores_configuration_contents(self):
        blob = json.dumps(run_arm.host_config_provenance())
        for leak in ("apiKey", "token", "oauth", "-----BEGIN"):
            self.assertNotIn(leak, blob)


class TestFixtureV3Determinism(unittest.TestCase):
    def test_materialized_commit_matches_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            self.assertEqual(materialize(target), MANIFEST["target_initial_commit"])

    def test_fixture_identity_and_pins(self):
        self.assertEqual(MANIFEST["fixture"], "v3")
        self.assertEqual(MANIFEST["claude_code_version"], "2.1.245")
        self.assertEqual(MANIFEST["model_id"], "claude-sonnet-5")
        self.assertEqual(MANIFEST["fixed_compact_boundary"], "after_turn_14")
        self.assertEqual(MANIFEST["target_initial_commit"], "c95860f6314c944eb487748002672adea93b2db8")


class TestFixtureV3Canaries(unittest.TestCase):
    def test_task_contract_contains_no_exact_canaries(self):
        markers = load_markers()
        for relative in ("seed/docs/contract.md", "seed/docs/incident.md"):
            text = (FIXTURE / relative).read_text(encoding="utf-8")
            for token in markers.values():
                with self.subTest(file=relative, token=token):
                    self.assertNotIn(token, text)

    def test_recall_document_contains_all_canaries_once(self):
        text = (FIXTURE / "seed/docs/recall-tags.md").read_text(encoding="utf-8")
        for token in load_markers().values():
            with self.subTest(token=token):
                self.assertEqual(text.count(token), 1)

    def test_scripted_prompts_never_contain_canary_values(self):
        self.assertEqual(run_arm.prompt_canary_leaks(PROMPTS, load_markers()), [])

    def test_final_eight_window_is_exact(self):
        window = [n for n in range(0, 16) if run_arm.is_final_pre_compact_turn(n)]
        self.assertEqual(window, list(range(7, 15)))

    def test_probe_material_includes_recall_tags(self):
        self.assertTrue(run_arm._probe_material("/tmp/t/docs/recall-tags.md"))
        self.assertTrue(run_arm._probe_material("/tmp/t/.claude/context-guard/WORKING_STATE.md"))
        self.assertFalse(run_arm._probe_material("/tmp/t/src/routeforge/parse.py"))


class TestFixtureV3ArmIsolation(unittest.TestCase):
    def test_hook_settings_are_external_only_for_hook_arms(self):
        self.assertIsNone(run_arm.hook_settings_json("A", REPO_ROOT))
        self.assertIsNone(run_arm.hook_settings_json("B", REPO_ROOT))
        for arm in ("C", "D"):
            settings = json.loads(run_arm.hook_settings_json(arm, REPO_ROOT) or "{}")
            self.assertEqual(sorted(settings["hooks"]), ["PostCompact", "PreCompact", "SessionStart"])

    def test_no_arm_gets_target_settings_json(self):
        for arm in run_arm.ARMS:
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                target = Path(run_arm.prepare_target(arm, Path(tmp) / arm, REPO_ROOT)["target"])
                self.assertFalse((target / ".claude/settings.json").exists())

    def test_state_assets_match_arm_definition_before_model_runs(self):
        expected = {"A": False, "B": True, "C": True, "D": False}
        markers = load_markers()
        for arm, should_exist in expected.items():
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                target = Path(run_arm.prepare_target(arm, Path(tmp) / arm, REPO_ROOT)["target"])
                snapshot = run_arm.state_snapshot(target, markers)
                self.assertEqual(snapshot["exists"], should_exist)

    def test_manipulation_check_requires_all_canaries_for_b_and_c(self):
        complete = {"exists": True, "markers": {name: True for name in load_markers()}, "chars": 100}
        partial = {"exists": True, "markers": {name: name != "goal" for name in load_markers()}, "chars": 100}
        absent = {"exists": False, "markers": None, "chars": 0}
        self.assertTrue(run_arm.state_manipulation_valid("B", complete))
        self.assertTrue(run_arm.state_manipulation_valid("C", complete))
        self.assertFalse(run_arm.state_manipulation_valid("B", partial))
        self.assertTrue(run_arm.state_manipulation_valid("A", absent))
        self.assertTrue(run_arm.state_manipulation_valid("D", absent))
        self.assertFalse(run_arm.state_manipulation_valid("D", complete))

    def test_hook_argv_uses_inline_settings(self):
        settings = run_arm.hook_settings_json("C", REPO_ROOT)
        argv = run_arm.claude_argv("hello", "claude-sonnet-5", settings_json=settings)
        self.assertIn("--settings", argv)
        self.assertNotIn(".claude/settings.json", " ".join(argv))


class TestFixtureV3SemanticProbe(unittest.TestCase):
    def test_answer_key_is_not_in_target(self):
        for arm in run_arm.ARMS:
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                target = Path(run_arm.prepare_target(arm, Path(tmp) / arm, REPO_ROOT)["target"])
                self.assertEqual(list(target.rglob("semantic_answers.json")), [])

    def test_semantic_scorer_exact_success(self):
        text = "Q1=B\nQ2=C\nQ3=A\nQ4=B\nQ5=C\nQ6=A\n"
        result = run_arm.score_semantic(text)
        self.assertEqual(result["hits"], 6)
        self.assertEqual(result["score"], 1.0)
        self.assertTrue(all(result["correct"].values()))

    def test_semantic_scorer_rejects_missing_or_duplicate_answers(self):
        result = run_arm.score_semantic("Q1=B\nQ1=B\nQ2=C\n")
        self.assertIsNone(result["answers"]["Q1"])
        self.assertLess(result["score"], 1.0)


class TestFixtureV3Validity(unittest.TestCase):
    def test_validity_requires_manipulation_and_no_echoes(self):
        record = run_arm.new_run_record("B", scored=False)
        record.update(
            {
                "substantive_turns_after_state": list(range(3, 15)),
                "marker_bearing_reads_in_final_8": [{"turn": n, "reads": []} for n in range(7, 15)],
                "marker_echoes_in_final_8": [{"turn": n, "markers": []} for n in range(7, 15)],
                "pre_boundary_compact_boundaries": [],
                "compact_boundary_events": [{}],
                "initial_tool_uses": 0,
                "state_manipulation_valid": True,
                "target_settings_present": False,
            }
        )
        self.assertTrue(run_arm._validity(record))
        record["marker_echoes_in_final_8"][0]["markers"] = ["goal"]
        self.assertFalse(run_arm._validity(record))

    def test_hook_arm_validity_requires_healthy_rehydrate(self):
        record = run_arm.new_run_record("C", scored=False)
        record.update(
            {
                "substantive_turns_after_state": list(range(3, 15)),
                "marker_bearing_reads_in_final_8": [{"turn": n, "reads": []} for n in range(7, 15)],
                "marker_echoes_in_final_8": [{"turn": n, "markers": []} for n in range(7, 15)],
                "pre_boundary_compact_boundaries": [],
                "compact_boundary_events": [{}],
                "initial_tool_uses": 0,
                "state_manipulation_valid": True,
                "target_settings_present": False,
                "hook_errors": 0,
                "rehydrate_context_chars": 5000,
            }
        )
        self.assertTrue(run_arm._validity(record))
        record["rehydrate_context_chars"] = 9001
        self.assertFalse(run_arm._validity(record))


if __name__ == "__main__":
    unittest.main()
