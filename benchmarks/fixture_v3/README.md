# Benchmark fixture v3

Fixture v3 is the pre-registered H1 long-distance survival fixture for Issue #21. It supersedes invalid fixture v2 without rewriting v2 history.

## What changed from v2

- Exact recall canaries live only in `seed/docs/recall-tags.md`; they are no longer task-working labels in the contract.
- The same turn-2 prompt exposes canaries to every arm once. B/C must preserve them in an already-existing WORKING_STATE; A/D must not create state.
- C/D hooks are passed with Claude Code `--settings` as inline JSON. No arm receives `.claude/settings.json` inside the target repository.
- The exact-canary probe remains the H1 primary metric.
- A second tools-disabled multiple-choice probe records semantic fact survival without LLM-as-judge.
- Final-eight rereads or canary echoes invalidate long-distance survival.

## Materialize target repository

```bash
python benchmarks/fixture_v3/materialize.py /tmp/routeforge-v3
```

The printed SHA must equal `manifest.json -> target_initial_commit`.

## Visible evaluator

From the materialized target:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Hidden evaluator

Run outside the target repository:

```bash
python benchmarks/fixture_v3/evaluate_hidden.py /tmp/routeforge-v3
```

Never copy the hidden evaluator, marker manifest, prompt manifest, or semantic answer key into the target.

## Unscored validity run

From a clean checkout with the pinned Claude Code version:

```bash
python -m benchmarks.fixture_v3.run_arm --all --dry-run
```

A scored pilot is blocked until all four arms complete and the protocol manipulation checks pass.

Required validity checks include:

- no pre-boundary compaction and exactly one scripted compact boundary;
- orientation uses no tools;
- at least 12 substantive turns after state establishment;
- no final-eight reads of contract / incident / recall-tags / WORKING_STATE;
- no final-eight recall-canary echoes;
- A/D have no WORKING_STATE before compact;
- B/C have WORKING_STATE and all six canaries before compact;
- target `.claude/settings.json` is absent in every arm;
- C/D hooks are healthy and rehydration stays within 9,000 characters;
- model and Claude Code version pins match.

## Outputs

Each run writes gitignored raw stream-json plus `run.json` under `benchmarks/runs/`.

Primary H1 fields:

- `survival_markers`
- `survival_score`
- `long_distance_valid`

Secondary semantic fields:

- `semantic_probe.answers`
- `semantic_probe.correct`
- `semantic_probe.score`

The dry run validates instrumentation only. Do not interpret arm ordering or survival values as efficacy evidence.
