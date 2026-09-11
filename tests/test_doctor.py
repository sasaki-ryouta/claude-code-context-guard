"""`doctor` must validate an installation without changing it (SPEC 14)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _support import SAMPLE_STATE, SRC_DIR, init_git_repo, write_working_state

from context_guard import state


def run_doctor(cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [sys.executable, "-m", "context_guard", "doctor"],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


class TestDoctor(unittest.TestCase):
    def test_healthy_installation_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, SAMPLE_STATE)
            (cwd / ".claude" / "settings.json").write_text(
                json.dumps({"hooks": {"PreCompact": [], "SessionStart": [], "PostCompact": []}})
            )

            result = run_doctor(cwd)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("WORKING_STATE", result.stdout)

    def test_oversized_state_is_reported_as_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, "x" * (state.WORKING_STATE_BUDGET + 1))

            result = run_doctor(cwd)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("budget", result.stdout.lower())

    def test_doctor_does_not_modify_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            before = {
                p: p.stat().st_mtime_ns for p in sorted(cwd.rglob("*")) if p.is_file()
            }

            run_doctor(cwd)

            after = {p: p.stat().st_mtime_ns for p in sorted(cwd.rglob("*")) if p.is_file()}
            self.assertEqual(before, after)

    def test_missing_state_is_reported_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_doctor(Path(tmp))
            self.assertIn("WORKING_STATE", result.stdout)


if __name__ == "__main__":
    unittest.main()
