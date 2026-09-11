"""`doctor` validates a real installation without changing it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _support import (
    SAMPLE_STATE,
    SRC_DIR,
    init_git_repo,
    write_runtime_gitignore,
    write_valid_settings,
    write_working_state,
)
from context_guard import state


def run_doctor(cwd: Path, *, project_dir: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run([sys.executable, "-m", "context_guard", "doctor"], cwd=cwd, capture_output=True, text=True, env=env, timeout=60)


class TestDoctor(unittest.TestCase):
    def test_healthy_git_installation_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_runtime_gitignore(cwd)
            write_working_state(cwd, SAMPLE_STATE)
            write_valid_settings(cwd)
            result = run_doctor(cwd)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Hook configuration: ok", result.stdout)
            self.assertIn("Runtime gitignore: ok", result.stdout)

    def test_unignored_runtime_state_fails_in_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, SAMPLE_STATE)
            write_valid_settings(cwd)
            result = run_doctor(cwd)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Runtime gitignore: unsafe", result.stdout)
            self.assertIn("WORKING_STATE.md", result.stdout)
            self.assertIn("sessions/", result.stdout)

    def test_non_git_project_does_not_require_gitignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            write_valid_settings(cwd)
            result = run_doctor(cwd)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Runtime gitignore: not applicable", result.stdout)

    def test_empty_hook_arrays_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            (cwd / ".claude" / "settings.json").write_text(json.dumps({"hooks":{"PreCompact":[],"SessionStart":[],"PostCompact":[]}}), encoding="utf-8")
            self.assertNotEqual(run_doctor(cwd).returncode, 0)

    def test_wrong_matcher_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            path = write_valid_settings(cwd)
            settings = json.loads(path.read_text(encoding="utf-8"))
            settings["hooks"]["SessionStart"][0]["matcher"] = "startup"
            path.write_text(json.dumps(settings), encoding="utf-8")
            result = run_doctor(cwd)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SessionStart", result.stdout)

    def test_wrong_subcommand_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            path = write_valid_settings(cwd)
            settings = json.loads(path.read_text(encoding="utf-8"))
            settings["hooks"]["PostCompact"][0]["hooks"][0]["command"] = "python3 -m context_guard pre-compact"
            path.write_text(json.dumps(settings), encoding="utf-8")
            result = run_doctor(cwd)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PostCompact", result.stdout)

    def test_oversized_state_is_reported_as_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, "x" * (state.WORKING_STATE_BUDGET + 1))
            write_valid_settings(cwd)
            result = run_doctor(cwd)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("budget", result.stdout.lower())

    def test_missing_state_is_an_installation_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_valid_settings(cwd)
            result = run_doctor(cwd)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WORKING_STATE: missing", result.stdout)

    def test_doctor_does_not_modify_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            write_valid_settings(cwd)
            before = {p:p.stat().st_mtime_ns for p in sorted(cwd.rglob("*")) if p.is_file()}
            run_doctor(cwd)
            after = {p:p.stat().st_mtime_ns for p in sorted(cwd.rglob("*")) if p.is_file()}
            self.assertEqual(before, after)

    def test_project_dir_is_used_when_doctor_runs_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            nested = root / "nested"
            nested.mkdir(parents=True)
            write_working_state(root, SAMPLE_STATE)
            write_valid_settings(root)
            result = run_doctor(nested, project_dir=root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(str(root.resolve()), result.stdout)


if __name__ == "__main__":
    unittest.main()
