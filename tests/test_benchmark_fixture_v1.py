from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmarks.fixture_v1.evaluate_hidden import evaluate
from benchmarks.fixture_v1.materialize import materialize
from benchmarks.fixture_v1.score_markers import load_markers, score_text


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (REPO_ROOT / "benchmarks" / "fixture_v1" / "manifest.json").read_text(encoding="utf-8")
)


class TestFixtureV1Determinism(unittest.TestCase):
    def test_materialized_git_commit_is_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "routeforge"
            actual = materialize(target)
            self.assertEqual(actual, MANIFEST["target_initial_commit"])

    def test_visible_suite_starts_with_known_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "routeforge"
            materialize(target)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(target / "src")
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=target,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("test_legacy_b_empty_account_is_rejected", output)

    def test_hidden_evaluator_rejects_seed_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "routeforge"
            materialize(target)
            result = evaluate(target)
            self.assertFalse(result["pass"])
            checks = result["checks"]
            self.assertFalse(checks["legacy_b_preserves_identifier_case"]["pass"])
            self.assertFalse(checks["equal_routing_keys_are_stable"]["pass"])
            self.assertFalse(checks["cache_preserves_identifier_case"]["pass"])
            self.assertFalse(checks["export_preserves_case_and_shape"]["pass"])
            self.assertFalse(checks["parsers_use_canonical_boundary"]["pass"])
            self.assertFalse(checks["exporter_does_not_renormalize"]["pass"])


class TestFixtureV1MarkerScoring(unittest.TestCase):
    def test_exact_marker_score_requires_exact_tokens(self):
        markers = load_markers()
        text = "I remember CGV1-GOAL-7F3A and CGV1-NEXT-4D88 only."
        result = score_text(text, markers)
        self.assertEqual(result["hits"], 2)
        self.assertEqual(result["total"], 6)
        self.assertAlmostEqual(result["score"], 2 / 6)
        self.assertTrue(result["markers"]["goal"])
        self.assertTrue(result["markers"]["next"])
        self.assertFalse(result["markers"]["decision"])

    def test_similar_but_inexact_token_does_not_count(self):
        markers = load_markers()
        result = score_text("CGV1-GOAL-7F3X", markers)
        self.assertEqual(result["hits"], 0)
        self.assertEqual(result["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
