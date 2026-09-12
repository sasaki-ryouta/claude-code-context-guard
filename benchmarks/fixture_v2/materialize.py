from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SEED = HERE / "seed"
COMMIT_MESSAGE = "benchmark fixture v1 seed"
FIXED_DATE = "2000-01-01T00:00:00Z"


def _run(argv: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return completed.stdout.strip()


def materialize(destination: Path) -> str:
    destination = destination.resolve()
    if destination.exists():
        if any(destination.iterdir()):
            raise ValueError(f"destination is not empty: {destination}")
    else:
        destination.mkdir(parents=True)

    shutil.copytree(SEED, destination, dirs_exist_ok=True)

    _run(["git", "init", "-b", "main"], destination)
    _run(["git", "config", "core.autocrlf", "false"], destination)
    _run(["git", "config", "core.filemode", "false"], destination)
    _run(["git", "config", "commit.gpgsign", "false"], destination)
    _run(["git", "add", "-A"], destination)

    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "Context Guard Benchmark",
            "GIT_AUTHOR_EMAIL": "benchmark@example.invalid",
            "GIT_COMMITTER_NAME": "Context Guard Benchmark",
            "GIT_COMMITTER_EMAIL": "benchmark@example.invalid",
            "GIT_AUTHOR_DATE": FIXED_DATE,
            "GIT_COMMITTER_DATE": FIXED_DATE,
        }
    )
    _run(["git", "commit", "-m", COMMIT_MESSAGE], destination, env=env)
    return _run(["git", "rev-parse", "HEAD"], destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize deterministic RouteForge benchmark fixture v1")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(materialize(args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
