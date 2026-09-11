"""Project state must remain stable when the hook cwd changes."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import SAMPLE_STATE, init_git_repo, load_fixture, run_cli, write_working_state
from context_guard import project, storage


class TestProjectRootResolution(unittest.TestCase):
    def test_git_subdirectory_resolves_to_repository_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)
            nested = root / "src" / "pkg"
            nested.mkdir(parents=True)
            self.assertEqual(project.resolve_project_root(nested), root.resolve())

    def test_valid_project_dir_hint_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            nested = root / "deep"
            nested.mkdir(parents=True)
            self.assertEqual(project.resolve_project_root(nested, str(root)), root.resolve())

    def test_invalid_project_dir_hint_falls_back_to_git_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)
            nested = root / "subdir"
            nested.mkdir()
            self.assertEqual(project.resolve_project_root(nested, str(root / "missing")), root.resolve())

    def test_precompact_after_cd_uses_root_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)
            write_working_state(root, SAMPLE_STATE)
            nested = root / "src"
            nested.mkdir()
            payload = load_fixture("pre_compact.json", cwd=str(nested))
            result = run_cli("pre-compact", json.dumps(payload))
            self.assertEqual(result.returncode, 0, result.stderr)
            session = storage.session_dir(root, payload["session_id"])
            checkpoint = json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["project_root"], str(root.resolve()))
            self.assertEqual(checkpoint["cwd"], str(nested))
            self.assertTrue(checkpoint["working_state"]["exists"])
            self.assertFalse((nested / ".claude" / "context-guard").exists())

    def test_non_git_nested_cwd_uses_claude_project_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            nested = root / "nested"
            nested.mkdir(parents=True)
            write_working_state(root, SAMPLE_STATE)
            payload = load_fixture("pre_compact.json", cwd=str(nested))
            result = run_cli("pre-compact", json.dumps(payload), extra_env={"CLAUDE_PROJECT_DIR": str(root)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((storage.session_dir(root, payload["session_id"]) / "checkpoint.json").is_file())
            self.assertFalse((nested / ".claude" / "context-guard").exists())


if __name__ == "__main__":
    unittest.main()
