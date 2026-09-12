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


class TestHostConfigurationIsolation(unittest.TestCase):
    """Host user settings load plugins/hooks that inject foreign context.

    Observed in the pre-control diagnostic run: a host SessionStart plugin hook
    injected the *previous arm's* session summary into the next arm's very first
    turn (A -> B -> C -> D). That is a direct cross-arm leak and destroys the
    causal comparison, so isolation is a validity requirement, not hygiene.
    """

    def _argv(self, settings_json=None):
        return run_arm.claude_argv(
            "p", "claude-sonnet-5", settings_json=settings_json
        )

    def test_every_invocation_restricts_setting_sources(self):
        argv = self._argv()
        self.assertIn("--setting-sources", argv)
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project")

    def test_restriction_applies_to_hook_arms_too(self):
        argv = self._argv(settings_json='{"hooks":{}}')
        self.assertIn("--setting-sources", argv)
        self.assertIn("--settings", argv)

    def test_bare_mode_is_not_used(self):
        # --bare would change the authentication path mid-series.
        self.assertNotIn("--bare", self._argv())

    def test_provenance_records_the_isolation_control(self):
        record = run_arm.new_run_record("A", scored=False)
        self.assertEqual(record["setting_sources_control"], "project")
        for field in ("host_surface_observed", "unexpected_hooks"):
            self.assertIn(field, record)

    def test_host_surface_is_extracted_from_init(self):
        init = {
            "type": "system",
            "subtype": "init",
            "plugins": [{"name": "x"}],
            "skills": ["a", "b"],
            "mcp_servers": [{"name": "m"}],
        }
        surface = run_arm.host_surface([init])
        self.assertEqual(surface, {"plugins": 1, "skills": 2, "mcp_servers": 1})

    def test_foreign_hooks_are_collected(self):
        events = [
            {"type": "system", "subtype": "hook_started", "hook_name": "SessionStart:startup"},
            {"type": "system", "subtype": "hook_started", "hook_name": "PreCompact:manual"},
        ]
        self.assertEqual(
            run_arm.foreign_hooks(events, arm="A"), ["SessionStart:startup", "PreCompact:manual"]
        )
        # Context Guard's own hooks are expected in the hook arms.
        self.assertEqual(run_arm.foreign_hooks(events, arm="C"), [])


class TestStateWritabilityUnderIsolation(unittest.TestCase):
    """Isolation must not remove the treatment it is supposed to measure.

    `.claude/` is a built-in sensitive path: with host settings excluded, the
    model's WORKING_STATE write is denied and arms B/C silently lose the very
    behaviour under test. The first isolated run failed its manipulation check
    for exactly this reason - every canary absent, state file present but never
    filled in.
    """

    def test_every_invocation_sets_an_explicit_permission_mode(self):
        argv = run_arm.claude_argv("p", "claude-sonnet-5", settings_json=None)
        self.assertIn("--permission-mode", argv)
        self.assertEqual(argv[argv.index("--permission-mode") + 1], run_arm.PERMISSION_MODE)

    def test_permission_mode_is_identical_for_every_arm(self):
        # A difference here would be a treatment difference, not a control.
        modes = set()
        for settings in (None, '{"hooks":{}}'):
            argv = run_arm.claude_argv("p", "claude-sonnet-5", settings_json=settings)
            modes.add(argv[argv.index("--permission-mode") + 1])
        self.assertEqual(len(modes), 1)

    def test_permission_mode_is_not_a_blanket_bypass(self):
        self.assertNotEqual(run_arm.PERMISSION_MODE, "bypassPermissions")

    def test_provenance_records_the_permission_mode(self):
        self.assertEqual(
            run_arm.new_run_record("B", scored=False)["permission_mode_control"],
            run_arm.PERMISSION_MODE,
        )


class TestFinalEightDetectionIsToolAgnostic(unittest.TestCase):
    """Distance is broken by *touching* the material, whatever tool did it.

    Detection previously inspected only Read.file_path and Bash.command, so a
    final-eight Grep over the contract returned reads=[] and echoes=[] and the
    run stayed valid - recently retrieved canaries masquerading as
    long-distance survival.
    """

    def _turn(self, tool: str, payload: dict, result_text: str = "") -> list[dict]:
        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": tool, "input": payload}
                    ]
                },
            }
        ]
        if result_text:
            events.append(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {"type": "tool_result", "tool_use_id": "t1", "content": result_text}
                        ]
                    },
                }
            )
        return events

    def test_grep_over_marker_material_counts_as_a_reread(self):
        events = self._turn("Grep", {"pattern": "CGV2", "path": "docs/contract.md"})
        self.assertTrue(run_arm.probe_material_reads(events))

    def test_glob_over_marker_material_counts_as_a_reread(self):
        events = self._turn("Glob", {"pattern": "docs/recall-tags.md"})
        self.assertTrue(run_arm.probe_material_reads(events))

    def test_unknown_future_tool_touching_the_material_is_caught(self):
        events = self._turn("SomeNewReaderTool", {"target": "docs/incident.md"})
        self.assertTrue(run_arm.probe_material_reads(events))

    def test_bare_filename_reference_is_caught(self):
        # Serializing the input appends quotes/braces, so an endswith() check
        # silently stopped matching: `cd .claude/context-guard && head
        # WORKING_STATE.md` evaded detection entirely.
        events = self._turn(
            "Bash", {"command": "cd .claude/context-guard && head -n 10 WORKING_STATE.md"}
        )
        self.assertTrue(run_arm.probe_material_reads(events))

    def test_bare_filename_in_any_field_is_caught(self):
        events = self._turn("SomeReader", {"target": "WORKING_STATE.md", "limit": 10})
        self.assertTrue(run_arm.probe_material_reads(events))

    def test_every_marker_document_is_caught_by_bare_filename(self):
        # Path-qualified needles missed `cd docs && cat contract.md`, whose
        # contents carry the semantic answers even though no canary appears.
        for filename in ("contract.md", "incident.md", "recall-tags.md", "WORKING_STATE.md"):
            with self.subTest(filename=filename):
                events = self._turn("Bash", {"command": f"cd docs && cat {filename}"})
                self.assertTrue(
                    run_arm.probe_material_reads(events), f"{filename} evaded detection"
                )

    def test_every_marker_document_is_caught_with_a_path(self):
        for path in (
            "docs/contract.md",
            "docs/incident.md",
            "docs/recall-tags.md",
            ".claude/context-guard/WORKING_STATE.md",
        ):
            with self.subTest(path=path):
                events = self._turn("Read", {"file_path": f"/tmp/target/{path}"})
                self.assertTrue(run_arm.probe_material_reads(events), f"{path} evaded detection")

    def test_marker_material_names_are_declared_in_one_place(self):
        # A second list is how contract.md ended up covered and incident.md did not.
        self.assertEqual(
            sorted(run_arm.MARKER_MATERIAL_FILENAMES),
            ["WORKING_STATE.md", "contract.md", "incident.md", "recall-tags.md"],
        )

    def test_ordinary_source_access_is_not_flagged(self):
        events = self._turn("Grep", {"pattern": "normalize", "path": "src/routeforge"})
        self.assertEqual(run_arm.probe_material_reads(events), [])

    def test_canary_returned_in_a_tool_result_counts_as_an_echo(self):
        markers = load_markers()
        token = markers["goal"]
        events = self._turn(
            "Grep", {"pattern": "CGV2", "path": "src"}, result_text=f"match: {token}"
        )
        self.assertIn("goal", run_arm.marker_echoes(events, markers))

    def test_clean_turn_has_no_echo(self):
        markers = load_markers()
        events = self._turn("Grep", {"pattern": "normalize", "path": "src"}, result_text="no matches")
        self.assertEqual(run_arm.marker_echoes(events, markers), [])


class TestProbeMeasuresMemoryNotRetrieval(unittest.TestCase):
    """A probe that can fetch the answer is not measuring survival.

    Denylisting tool names cannot be complete: retrieval paths such as
    TaskOutput remain available, and new tools can appear in any Claude Code
    release. The invariant that actually holds is behavioural - the probe must
    use no tools at all - so validity is judged on observed tool use rather
    than on the denylist being exhaustive.
    """

    def _valid_record(self) -> dict:
        record = {
            "arm": "B",
            "substantive_turns_after_state": list(range(3, 15)),
            "marker_bearing_reads_in_final_8": [{"turn": n, "reads": []} for n in range(7, 15)],
            "marker_echoes_in_final_8": [{"turn": n, "markers": []} for n in range(7, 15)],
            "pre_boundary_compact_boundaries": [],
            "compact_boundary_events": [{}],
            "initial_tool_uses": 0,
            "state_manipulation_valid": True,
            "target_settings_present": False,
            "auto_memory_control": "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1",
            "setting_sources_control": "project",
            "permission_mode_control": run_arm.PERMISSION_MODE,
            "host_surface_observed": {"plugins": 0, "skills": 20, "mcp_servers": 0},
            "unexpected_hooks": [],
            "probe_tool_uses": 0,
            "semantic_probe_tool_uses": 0,
        }
        return record

    def test_clean_probe_is_valid(self):
        self.assertTrue(run_arm._validity(self._valid_record()))

    def test_any_tool_use_during_the_primary_probe_invalidates_the_run(self):
        record = self._valid_record()
        record["probe_tool_uses"] = 1
        self.assertFalse(run_arm._validity(record))

    def test_any_tool_use_during_the_semantic_probe_invalidates_the_run(self):
        record = self._valid_record()
        record["semantic_probe_tool_uses"] = 1
        self.assertFalse(run_arm._validity(record))

    def test_unrecorded_probe_tool_use_invalidates_the_run(self):
        # Absent evidence is not evidence of a clean probe.
        record = self._valid_record()
        record["probe_tool_uses"] = None
        self.assertFalse(run_arm._validity(record))

    def test_known_retrieval_tools_are_also_denied_up_front(self):
        denied = set(run_arm.PROBE_DISALLOWED_TOOLS)
        for tool in ("TaskOutput", "Task", "Read", "Bash", "Glob", "Grep", "WebFetch", "WebSearch"):
            with self.subTest(tool=tool):
                self.assertIn(tool, denied)

    def test_provenance_carries_probe_tool_counts(self):
        record = run_arm.new_run_record("C", scored=False)
        for field in ("probe_tool_uses", "semantic_probe_tool_uses"):
            self.assertIn(field, record)


class TestValidityRejectsUncontrolledRuns(unittest.TestCase):
    def _valid_record(self) -> dict:
        return {
            "arm": "A",
            "substantive_turns_after_state": list(range(3, 15)),
            "marker_bearing_reads_in_final_8": [{"turn": n, "reads": []} for n in range(7, 15)],
            "marker_echoes_in_final_8": [{"turn": n, "markers": []} for n in range(7, 15)],
            "pre_boundary_compact_boundaries": [],
            "compact_boundary_events": [{}],
            "initial_tool_uses": 0,
            "state_manipulation_valid": True,
            "target_settings_present": False,
            "auto_memory_control": "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1",
            "setting_sources_control": "project",
            "host_surface_observed": {"plugins": 0, "skills": 0, "mcp_servers": 0},
            "unexpected_hooks": [],
            "probe_tool_uses": 0,
            "semantic_probe_tool_uses": 0,
        }

    def test_baseline_record_is_valid(self):
        self.assertTrue(run_arm._validity(self._valid_record()))

    def test_record_without_the_auto_memory_control_is_rejected(self):
        # Historical runs predate the control and must not machine-validate.
        record = self._valid_record()
        del record["auto_memory_control"]
        self.assertFalse(run_arm._validity(record))

    def test_explicitly_disabled_control_is_rejected(self):
        record = self._valid_record()
        record["auto_memory_control"] = "CLAUDE_CODE_DISABLE_AUTO_MEMORY=0"
        self.assertFalse(run_arm._validity(record))

    def test_record_without_setting_source_isolation_is_rejected(self):
        record = self._valid_record()
        record["setting_sources_control"] = None
        self.assertFalse(run_arm._validity(record))

    def test_bundled_skills_do_not_invalidate_a_run(self):
        # Claude Code ships its own skills; they load identically in every arm
        # and are not a host-configuration leak.
        record = self._valid_record()
        record["host_surface_observed"] = {"plugins": 0, "skills": 20, "mcp_servers": 0}
        self.assertTrue(run_arm._validity(record))

    def test_observed_host_surface_invalidates_the_run(self):
        for key in ("plugins", "mcp_servers"):
            with self.subTest(surface=key):
                record = self._valid_record()
                record["host_surface_observed"] = {**record["host_surface_observed"], key: 1}
                self.assertFalse(run_arm._validity(record))

    def test_foreign_hook_execution_invalidates_the_run(self):
        record = self._valid_record()
        record["unexpected_hooks"] = ["SessionStart:startup"]
        self.assertFalse(run_arm._validity(record))

    def test_historical_pre_control_records_do_not_validate(self):
        import glob

        runs = sorted(glob.glob(str(REPO_ROOT / "benchmarks" / "runs" / "*" / "*" / "run.json")))
        checked = 0
        for path in runs:
            record = json.loads(Path(path).read_text(encoding="utf-8"))
            if record.get("auto_memory_control"):
                continue
            checked += 1
            self.assertFalse(
                run_arm._validity(record), f"uncontrolled run machine-validated: {path}"
            )
        if checked == 0:
            self.skipTest("no uncontrolled historical runs present")


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
                "host_surface_observed": {"plugins": 0, "skills": 0, "mcp_servers": 0},
                "unexpected_hooks": [],
                "probe_tool_uses": 0,
                "semantic_probe_tool_uses": 0,
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
                "host_surface_observed": {"plugins": 0, "skills": 0, "mcp_servers": 0},
                "unexpected_hooks": [],
                "probe_tool_uses": 0,
                "semantic_probe_tool_uses": 0,
            }
        )
        self.assertTrue(run_arm._validity(record))
        record["rehydrate_context_chars"] = 9001
        self.assertFalse(run_arm._validity(record))


if __name__ == "__main__":
    unittest.main()
