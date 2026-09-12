# Benchmark fixture v1

This directory implements the first v0.2 mechanism-isolation fixture described in `docs/benchmark-fixture-v1.md`.

## Materialize target repository

```bash
python benchmarks/fixture_v1/materialize.py /tmp/routeforge-v1
```

The printed SHA must equal `manifest.json -> target_initial_commit`.

## Visible evaluator

From the materialized target:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The seed intentionally starts with a visible failure. The task is complete only after the visible and hidden evaluators pass.

## Hidden evaluator

Run outside the target repository:

```bash
python benchmarks/fixture_v1/evaluate_hidden.py /tmp/routeforge-v1
```

Do not copy `evaluate_hidden.py` into the target repo or expose it to the benchmark agent.

## Marker scorer

Save the tools-disabled post-compact probe response to a file, then:

```bash
python benchmarks/fixture_v1/score_markers.py probe.txt
```

Primary survival is exact token presence. Semantic/rubric scoring is secondary only.

## Pinned inputs

- `prompts.json`: initial prompt, scripted turns, post-compact probe, resume prompt
- `markers.json`: survival tokens
- `manifest.json`: Claude Code pin, compact boundary, deterministic target commit
- `seed/`: source snapshot used to create the target repository

`manifest.json` intentionally leaves `model_id` null until the exact model identifier is verified locally. A scored pilot must not start while it is null.
