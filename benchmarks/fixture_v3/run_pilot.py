"""Execute the pre-registered H1 scored pilot.

The schedule, replacement policy, and caps come from
docs/h1-pilot-preregistration.md and are not parameters: nothing here may be
tuned once scoring starts. Aggregation lives in aggregate_pilot.py so that
executing the pilot cannot be confused with deciding its outcome.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import run_arm

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

RANDOMIZATION_SEED = 20260913
BLOCKS = 5
CONTROL_ARMS_AFTER_BLOCK = 3
MAX_REPLACEMENTS = 2
SCHEDULED_RUNS = 12


def scheduled_order(seed: int = RANDOMIZATION_SEED) -> list[str]:
    """The registered run order, reproduced from the recorded seed."""
    rng = random.Random(seed)
    order: list[str] = []
    for block in range(1, BLOCKS + 1):
        pair = ["B", "C"]
        rng.shuffle(pair)
        order.extend(pair)
        if block == CONTROL_ARMS_AFTER_BLOCK:
            order.extend(["A", "D"])
    return order


def is_valid(record: dict[str, Any]) -> bool:
    return record.get("aborted_reason") is None and record.get("long_distance_valid") is True


def run_pilot(output_root: Path) -> dict[str, Any]:
    order = scheduled_order()
    assert len(order) == SCHEDULED_RUNS, order

    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    runs: list[dict[str, Any]] = []
    replacements_used = 0
    halted: str | None = None

    for position, arm in enumerate(order, start=1):
        record = run_arm.run_one_arm(
            arm,
            output_root=output_root,
            scored=True,
            keep_target=False,
            run_timestamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        )
        runs.append({"position": position, "arm": arm, "replacement_for": None, "record": record})

        # Replacement is mandatory and immediate: it happens before the next
        # scheduled run and before anything is aggregated, so the decision to
        # re-run can never depend on how the results are turning out.
        if not is_valid(record):
            if replacements_used >= MAX_REPLACEMENTS:
                halted = "HARD_BLOCKER: too many invalid runs"
                break
            # Keep replacing while the budget allows: an invalid replacement is
            # itself an exclusion and consumes the next retry immediately,
            # rather than deferring it to a later scheduled position.
            replaced_ok = False
            while replacements_used < MAX_REPLACEMENTS:
                replacements_used += 1
                replacement = run_arm.run_one_arm(
                    arm,
                    output_root=output_root,
                    scored=True,
                    keep_target=False,
                    run_timestamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                )
                runs.append(
                    {"position": position, "arm": arm, "replacement_for": position, "record": replacement}
                )
                if is_valid(replacement):
                    replaced_ok = True
                    break
            if not replaced_ok:
                halted = "HARD_BLOCKER: too many invalid runs"
                break

    return {
        "pilot": "h1-v3",
        "preregistration": "docs/h1-pilot-preregistration.md",
        "fixture_commit_expected": "ca5e677b1a448c1a91ac0bbd2f02644404d45855",
        "randomization_seed": RANDOMIZATION_SEED,
        "scheduled_order": order,
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "replacements_used": replacements_used,
        "halted": halted,
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the pre-registered H1 scored pilot")
    parser.add_argument("--output-root", type=Path, default=Path("benchmarks/runs/h1-pilot"))
    args = parser.parse_args(argv)

    result = run_pilot(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    path = args.output_root / "pilot.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return 1 if result["halted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
