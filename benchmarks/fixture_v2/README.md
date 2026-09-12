# Benchmark fixture v2

This directory is the repaired long-distance survival fixture for Issue #19 / #13. It versions the invalid v1 protocol rather than editing v1 in place.

v2 is intentionally a **mechanism-isolation fixture for H1**. Task-outcome sensitivity (H3) is tracked separately in Issue #18 so the task is not made harder after observing v1 arm outcomes.

## What changed from v1

- the orientation message is tool-disabled and must not start repository work;
- the turn-14 token-suppression contradiction is removed;
- the six primary tokens now represent only durable state that should remain valid at the compact boundary;
- final-eight assistant responses are checked for marker echoes, not only marker-bearing file rereads;
- auto compaction uses the documented `DISABLE_AUTO_COMPACT=1` control;
- `system/compact_boundary` stream events are counted for every arm;
- the actual Claude Code version is checked before and after each run;
- `DISABLE_AUTOUPDATER=1` prevents a binary update between resumed print-mode invocations;
- tracked dirty fixture-source state aborts the run.

## Materialize target repository

```bash
python benchmarks/fixture_v2/materialize.py /tmp/routeforge-v2
```

The printed SHA must equal `manifest.json -> target_initial_commit`.

## Unit/evaluator checks

From the materialized target:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The hidden evaluator remains outside the target repository:

```bash
python benchmarks/fixture_v2/evaluate_hidden.py /tmp/routeforge-v2
```

Do not copy `evaluate_hidden.py`, `markers.json`, or `prompts.json` into the target.

## Unscored A/B/C/D dry run

Only from a clean checkout at the exact fixture commit:

```bash
python -m benchmarks.fixture_v2.run_arm --all --dry-run
```

The run is not eligible for a scored pilot unless every arm completes without `aborted_reason` and `long_distance_valid` is true. In particular there must be:

- zero pre-boundary `compact_boundary` events;
- exactly one boundary event around the scripted `/compact`;
- zero marker-bearing reads in the final eight scripted turns;
- zero assistant marker echoes in those final eight turns;
- at least 12 substantive post-state turns;
- zero tool calls during the orientation message.

For B/C, `state_markers_before_compact` is recorded separately from post-compact survival. This allows both end-to-end state-management quality and conditional rehydration fidelity to be analyzed without silently dropping missing state.

## Pinned inputs

- `prompts.json`: orientation, scripted turns, post-compact probe, resume prompt
- `markers.json`: six durable-state survival tokens
- `manifest.json`: Claude Code/model pins, compact boundary, deterministic target commit, compaction/update controls
- `seed/`: deterministic RouteForge source snapshot

No scored pilot starts until the v2 unscored dry run passes the validity gate.
