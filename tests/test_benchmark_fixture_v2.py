from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import REPO_ROOT

from benchmarks.fixture_v2 import run_arm
from benchmarks.fixture_v2.materialize import materialize
from benchmarks.fixture_v2.score_markers import load_markers, score_text


FIXTURE = REPO_ROOT / "benchmarks" / "fixture_v2"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
PROMPTS = json.loads((FIXTURE / "prompts.json").read_text(encoding="utf-8"))


class TestFixtureV2Pins(unittest.TestCase):
    def test_materialized_commit_matches_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(materialize(Path(tmp)), MANIFEST["target_initial_commit"])

    def test_environment_is_fully_pinned(self):
        self.assertEqual(MANIFEST["fixture"], "v2")
        self.assertEqual(MANIFEST["claude_code_version"], "2.1.245")
        self.assertEqual(MANIFEST["model_id"], "claude-sonnet-5")
        self.assertEqual(MANIFEST["fixed_compact_boundary"], "after_turn_14")
        self.assertEqual(MANIFEST["auto_compaction_control"], "DISABLE_AUTO_COMPACT=1")
        self.assertEqual(MANIFEST["auto_updater_control"], "DISABLE_AUTOUPDATER=1")

    def test_version_match_is_exact_on_version_token(self):
        self.assertTrue(run_arm.version_matches("2.1.245 (Claude Code)", "2.1.245"))
        self.assertFalse(run_arm.version_matches("2.1.246 (Claude Code)", "2.1.245"))


class TestFixtureV2Markers(unittest.TestCase):
    def test_primary_markers_are_six_durable_fields(self):
        markers = load_markers()
        self.assertEqual(
            set(markers),
            {"goal", "criterion", "decision", "identifier_case", "output_schema", "rejected"},
        )
        self.assertNotIn("failure", markers)
        self.assertNotIn("next", markers)

    def test_tokens_are_unique_and_v2_namespaced(self):
        tokens = list(load_markers().values())
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertTrue(all(token.startswith("CGV2-") for token in tokens))

    def test_scorer_is_exact_binary_presence(self):
        markers = load_markers()
        names = list(markers)
        text = f"remembered {markers[names[0]]} and {markers[names[2]]}"
        score = score_text(text, markers)
        self.assertEqual(score["hits"], 2)
        self.assertEqual(score["total"], 6)
        self.assertAlmostEqual(score["score"], 2 / 6)


class TestFixtureV2Protocol(unittest.TestCase):
    def test_orientation_and_fourteen_scripted_turns_are_distinct(self):
        self.assertEqual(len(PROMPTS["turns"]), 14)
        self.assertIn("orientation message only", PROMPTS["initial"])
        self.assertIn("reply READY", PROMPTS["initial"])
        self.assertIn("Inspect the repository structure", PROMPTS["turns"][0])

    def test_v1_probe_contradiction_is_gone(self):
        turn14 = PROMPTS["turns"][13].lower()
        self.assertNotIn("do not quote benchmark token", turn14)
        self.assertNotIn("even if you remember", turn14)
        self.assertIn("exact benchmark tokens", PROMPTS["probe"].lower())

    def test_prompts_never_embed_primary_tokens(self):
        self.assertEqual(run_arm.core.prompt_marker_leaks(PROMPTS, load_markers()), [])

    def test_final_eight_window_is_exact(self):
        window = [n for n in range(0, 16) if run_arm.is_final_pre_compact_turn(n)]
        self.assertEqual(window, list(range(7, 15)))

    def test_post_state_window_has_twelve_turns(self):
        window = [n for n in range(0, 16) if run_arm.is_post_state_turn(n)]
        self.assertEqual(window, list(range(3, 15)))


class TestFixtureV2ValiditySignals(unittest.TestCase):
    def test_compact_boundary_parser_is_arm_independent(self):
        events = [
            {"type": "assistant", "message": {"content": []}},
            {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "manual"}},
        ]
        self.assertEqual(len(run_arm.compact_boundaries(events)), 1)

    def test_marker_echo_detector_detects_assistant_text(self):
        markers = load_markers()
        token = markers["goal"]
        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": f"I remember {token}"}]},
            }
        ]
        self.assertEqual(run_arm.marker_echoes(events, markers), ["goal"])

    def test_marker_echo_detector_ignores_plain_semantics(self):
        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Preserve routing semantics."}]},
            }
        ]
        self.assertEqual(run_arm.marker_echoes(events, load_markers()), [])

    def test_state_marker_presence_is_non_invasive_file_check(self):
        markers = load_markers()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".claude" / "context-guard" / "WORKING_STATE.md"
            state.parent.mkdir(parents=True)
            state.write_text(markers["goal"] + "\n", encoding="utf-8")
            presence = run_arm.state_marker_presence(root, markers)
            self.assertIsNotNone(presence)
            self.assertTrue(presence["goal"])
            self.assertFalse(presence["criterion"])


if __name__ == "__main__":
    unittest.main()
