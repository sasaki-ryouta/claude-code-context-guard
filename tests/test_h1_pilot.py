"""The pilot must execute and decide exactly what was pre-registered."""

from __future__ import annotations

import json
import unittest
from fractions import Fraction
from pathlib import Path

from _support import REPO_ROOT

from benchmarks.fixture_v3 import aggregate_pilot, run_pilot

PREREG = (REPO_ROOT / "docs" / "h1-pilot-preregistration.md").read_text(encoding="utf-8")


def record(arm: str, survival: float | None, *, valid: bool = True, semantic: float | None = 1.0) -> dict:
    return {
        "arm": arm,
        "aborted_reason": None if valid else "boom",
        "long_distance_valid": valid,
        "survival_score": survival,
        "semantic_probe": {"score": semantic},
    }


def pilot(entries: list[tuple[str, float | None, bool]], **extra) -> dict:
    return {
        "pilot": "h1-v3",
        "replacements_used": extra.get("replacements_used", 0),
        "halted": extra.get("halted"),
        "runs": [
            {"position": i + 1, "arm": arm, "replacement_for": None, "record": record(arm, s, valid=v)}
            for i, (arm, s, v) in enumerate(entries)
        ],
    }


def balanced(b_scores: list[float], c_scores: list[float]) -> dict:
    entries: list[tuple[str, float | None, bool]] = []
    for b, c in zip(b_scores, c_scores):
        entries.append(("B", b, True))
        entries.append(("C", c, True))
    entries.append(("A", 0.0, True))
    entries.append(("D", 0.0, True))
    return pilot(entries)


class TestSchedule(unittest.TestCase):
    def test_order_matches_the_registered_sequence(self):
        self.assertEqual(
            run_pilot.scheduled_order(),
            ["C", "B", "C", "B", "C", "B", "A", "D", "B", "C", "B", "C"],
        )

    def test_order_is_reproducible_from_the_recorded_seed(self):
        self.assertEqual(run_pilot.scheduled_order(), run_pilot.scheduled_order())
        self.assertEqual(run_pilot.RANDOMIZATION_SEED, 20260913)

    def test_registered_order_appears_in_the_preregistration(self):
        self.assertIn("20260913", PREREG)

    def test_sample_allocation_matches_the_registration(self):
        order = run_pilot.scheduled_order()
        self.assertEqual(len(order), 12)
        self.assertEqual(order.count("B"), 5)
        self.assertEqual(order.count("C"), 5)
        self.assertEqual(order.count("A"), 1)
        self.assertEqual(order.count("D"), 1)

    def test_replacement_budget_is_two(self):
        self.assertEqual(run_pilot.MAX_REPLACEMENTS, 2)


class TestDecisionRules(unittest.TestCase):
    def test_adverse_contrast_stops_even_when_both_arms_are_saturated(self):
        # Rule 1 must precede saturation, or a clear adverse result could be
        # reported as inconclusive.
        result = aggregate_pilot.decide(balanced([1.0] * 5, [0.0] * 5))
        self.assertEqual(result["decision"], "STOP_NO_USEFUL_INCREMENT")
        self.assertTrue(result["rule"].startswith("1"))

    def test_equal_arms_stop(self):
        # Identical arms away from either extreme: no increment, and not a
        # saturation claim.
        result = aggregate_pilot.decide(balanced([0.5] * 5, [0.5] * 5))
        self.assertEqual(result["decision"], "STOP_NO_USEFUL_INCREMENT")
        self.assertTrue(result["rule"].startswith("2b"), result["rule"])

    def test_both_arms_saturated_is_inconclusive_ceiling(self):
        result = aggregate_pilot.decide(balanced([1.0] * 5, [1.0] * 5))
        self.assertEqual(result["decision"], "STOP_NO_USEFUL_INCREMENT")
        self.assertIn("CEILING", result["rule"])

    def test_high_baseline_alone_is_not_a_ceiling(self):
        # mean(B) high but C differs: that is a measurable contrast.
        result = aggregate_pilot.decide(balanced([1.0] * 5, [1.0, 1.0, 1.0, 1.0, 0.0]))
        self.assertTrue(result["rule"].startswith("1"))

    def test_large_consistent_increment_is_go(self):
        result = aggregate_pilot.decide(balanced([0.0] * 5, [1.0] * 5))
        self.assertEqual(result["decision"], "GO_EXTERNAL_VALIDATION")

    def test_large_but_inconsistent_increment_stops(self):
        # C wins two blocks by a lot and loses three narrowly: the mean clears
        # the threshold but the direction is not consistent.
        result = aggregate_pilot.decide(
            balanced([1 / 6, 1 / 6, 1 / 6, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0, 1.0])
        )
        self.assertEqual(result["decision"], "STOP_NO_USEFUL_INCREMENT")
        self.assertTrue(result["rule"].startswith("4"), result["rule"])

    def test_increment_below_one_canary_stops(self):
        # Away from both extremes, so saturation cannot claim this case.
        result = aggregate_pilot.decide(
            balanced([0.5] * 5, [0.5, 0.5, 0.5, 0.5, 2 / 3])
        )
        self.assertEqual(result["decision"], "STOP_NO_USEFUL_INCREMENT")
        self.assertTrue(result["rule"].startswith("5"), result["rule"])

    def test_threshold_is_an_exact_fraction(self):
        self.assertEqual(aggregate_pilot.GO_THRESHOLD, Fraction(1, 6))
        # Exactly one canary on average, consistently: GO.
        result = aggregate_pilot.decide(balanced([0.0] * 5, [1 / 6] * 5))
        self.assertEqual(result["decision"], "GO_EXTERNAL_VALIDATION")


class TestGuards(unittest.TestCase):
    def test_halted_pilot_reports_the_hard_blocker(self):
        data = balanced([0.0] * 5, [1.0] * 5)
        data["halted"] = "HARD_BLOCKER: too many invalid runs"
        self.assertIn("HARD_BLOCKER", aggregate_pilot.decide(data)["decision"])

    def test_insufficient_valid_runs_issues_no_decision(self):
        entries = [("B", 0.0, True)] * 4 + [("C", 1.0, True)] * 5
        result = aggregate_pilot.decide(pilot(entries))
        self.assertIn("HARD_BLOCKER", result["decision"])

    def test_invalid_runs_are_excluded_from_the_aggregate(self):
        data = balanced([0.0] * 5, [1.0] * 5)
        data["runs"].append(
            {"position": 13, "arm": "C", "replacement_for": 12, "record": record("C", 0.0, valid=False)}
        )
        result = aggregate_pilot.decide(data)
        self.assertEqual(result["valid_runs"]["C"], 5)
        self.assertEqual(result["decision"], "GO_EXTERNAL_VALIDATION")

    def test_secondary_scores_never_change_the_decision(self):
        strong_secondary = balanced([1.0] * 5, [0.0] * 5)
        for entry in strong_secondary["runs"]:
            if entry["arm"] == "C":
                entry["record"]["semantic_probe"] = {"score": 1.0}
            elif entry["arm"] == "B":
                entry["record"]["semantic_probe"] = {"score": 0.0}
        result = aggregate_pilot.decide(strong_secondary)
        self.assertEqual(result["decision"], "STOP_NO_USEFUL_INCREMENT")


if __name__ == "__main__":
    unittest.main()
