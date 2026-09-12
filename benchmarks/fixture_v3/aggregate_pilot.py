"""Aggregate the H1 pilot strictly under the pre-registered decision rules.

Kept separate from run_pilot.py: executing the pilot and deciding its outcome
are different acts, and the decision rules must be readable on their own.
"""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path
from statistics import mean
from typing import Any

# docs/h1-pilot-preregistration.md section 6. Exact fractions: 0.167 and 1/6
# differ at the decision boundary.
GO_THRESHOLD = Fraction(1, 6)
CEILING = Fraction(95, 100)
FLOOR = Fraction(5, 100)
MIN_VALID_PER_PRIMARY_ARM = 5
DIRECTIONAL_BLOCKS_REQUIRED = 4


def _valid_runs(pilot: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    return [
        entry["record"]
        for entry in pilot["runs"]
        if entry["arm"] == arm
        and entry["record"].get("aborted_reason") is None
        and entry["record"].get("long_distance_valid") is True
    ]


def _scores(records: list[dict[str, Any]], key: str) -> list[Fraction]:
    values: list[Fraction] = []
    for record in records:
        raw = record.get(key) if key == "survival_score" else (record.get("semantic_probe") or {}).get("score")
        if raw is None:
            continue
        values.append(Fraction(raw).limit_denominator(6))
    return values


def _matched_blocks(pilot: dict[str, Any]) -> list[tuple[Fraction | None, Fraction | None]]:
    """Pair each B with the C from the same block, in schedule order."""
    pairs: list[tuple[Fraction | None, Fraction | None]] = []
    pending: dict[str, Fraction | None] = {}
    for entry in pilot["runs"]:
        arm = entry["arm"]
        if arm not in ("B", "C"):
            continue
        record = entry["record"]
        valid = record.get("aborted_reason") is None and record.get("long_distance_valid") is True
        score = Fraction(record["survival_score"]).limit_denominator(6) if valid and record.get("survival_score") is not None else None
        pending[arm] = score
        if "B" in pending and "C" in pending:
            pairs.append((pending.pop("B"), pending.pop("C")))
    return pairs


def decide(pilot: dict[str, Any]) -> dict[str, Any]:
    b_valid = _valid_runs(pilot, "B")
    c_valid = _valid_runs(pilot, "C")
    b_scores = _scores(b_valid, "survival_score")
    c_scores = _scores(c_valid, "survival_score")

    result: dict[str, Any] = {
        "pilot": pilot.get("pilot"),
        "valid_runs": {"B": len(b_scores), "C": len(c_scores),
                       "A": len(_valid_runs(pilot, "A")), "D": len(_valid_runs(pilot, "D"))},
        "replacements_used": pilot.get("replacements_used"),
        "halted": pilot.get("halted"),
    }

    if pilot.get("halted"):
        result["decision"] = pilot["halted"]
        return result
    if len(b_scores) < MIN_VALID_PER_PRIMARY_ARM or len(c_scores) < MIN_VALID_PER_PRIMARY_ARM:
        result["decision"] = "HARD_BLOCKER: insufficient valid samples"
        return result

    mean_b = Fraction(sum(b_scores), len(b_scores))
    mean_c = Fraction(sum(c_scores), len(c_scores))
    d = mean_c - mean_b
    blocks = [(b, c) for b, c in _matched_blocks(pilot) if b is not None and c is not None]
    directional = sum(1 for b, c in blocks if c > b)

    result.update(
        {
            "primary": {
                "B": [str(s) for s in b_scores],
                "C": [str(s) for s in c_scores],
                "mean_B": float(mean_b),
                "mean_C": float(mean_c),
                "d": float(d),
                "d_exact": str(d),
                "matched_blocks_used": len(blocks),
                "blocks_favouring_C": directional,
            },
            "secondary": {
                "B": [float(s) for s in _scores(b_valid, "semantic")],
                "C": [float(s) for s in _scores(c_valid, "semantic")],
            },
        }
    )

    # Section 6, evaluated in order. An adverse contrast is decided BEFORE
    # saturation is considered, so a negative result can never be reported as
    # inconclusive. A zero contrast is decided AFTER saturation, so two arms
    # pinned at an extreme are recorded as a saturating instrument rather than
    # as a measured absence of effect - those are different claims.
    if d < 0:
        result["decision"] = "STOP_NO_USEFUL_INCREMENT"
        result["rule"] = "1: d < 0 (adverse contrast)"
    elif mean_b >= CEILING and mean_c >= CEILING:
        result["decision"] = "STOP_NO_USEFUL_INCREMENT"
        result["rule"] = "2: INCONCLUSIVE_CEILING - both arms saturated; no measurable increment because the instrument saturates"
    elif mean_b <= FLOOR and mean_c <= FLOOR:
        result["decision"] = "STOP_NO_USEFUL_INCREMENT"
        result["rule"] = "2: INCONCLUSIVE_FLOOR - both arms at floor; no measurable increment because the instrument saturates"
    elif d == 0:
        result["decision"] = "STOP_NO_USEFUL_INCREMENT"
        result["rule"] = "2b: d == 0 (no increment)"
    elif d >= GO_THRESHOLD and directional >= DIRECTIONAL_BLOCKS_REQUIRED:
        result["decision"] = "GO_EXTERNAL_VALIDATION"
        result["rule"] = "3: d >= 1/6 and directionally consistent"
    elif d >= GO_THRESHOLD:
        result["decision"] = "STOP_NO_USEFUL_INCREMENT"
        result["rule"] = "4: d >= 1/6 but not directionally consistent"
    else:
        result["decision"] = "STOP_NO_USEFUL_INCREMENT"
        result["rule"] = "5: 0 < d < 1/6"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate the H1 pilot under pre-registered rules")
    parser.add_argument("pilot", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    pilot = json.loads(args.pilot.read_text(encoding="utf-8"))
    result = decide(pilot)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
