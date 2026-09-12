# RouteForge benchmark fixture

This repository is generated for the Claude Code Context Guard v0.2 benchmark.

Use only the Python standard library. Do not use the network or install packages.

Visible evaluator:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The task is to complete the normalization migration while preserving public behavior. Hidden evaluator checks are intentionally not present in this target repository.
