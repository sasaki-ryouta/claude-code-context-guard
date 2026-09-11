"""Budget invariants: injected context must never exceed the caps in SPEC 2.2."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _support import SAMPLE_STATE, init_git_repo, write_working_state

from context_guard import git_state, state


class TestWorkingStateBudget(unittest.TestCase):
    def test_state_under_budget_is_untouched(self):
        kept, truncated = state.truncate_state(SAMPLE_STATE)
        self.assertEqual(kept, SAMPLE_STATE)
        self.assertFalse(truncated)

    def test_state_over_budget_is_cut_to_the_limit(self):
        huge = "x" * (state.WORKING_STATE_BUDGET * 3)
        kept, truncated = state.truncate_state(huge)
        self.assertTrue(truncated)
        self.assertLessEqual(len(kept), state.WORKING_STATE_BUDGET)

    def test_truncation_is_deterministic(self):
        huge = "y" * (state.WORKING_STATE_BUDGET + 500)
        self.assertEqual(state.truncate_state(huge), state.truncate_state(huge))

    def test_truncation_keeps_the_head_of_the_document(self):
        # Goal/acceptance criteria live at the top of WORKING_STATE.md (SPEC 5),
        # so a truncated state must still answer "what am I doing".
        huge = SAMPLE_STATE + "z" * (state.WORKING_STATE_BUDGET * 2)
        kept, _ = state.truncate_state(huge)
        self.assertIn("# Goal", kept)


class TestRecoveryContextBudget(unittest.TestCase):
    def _recovery(self, cwd: Path) -> str:
        return state.build_recovery_context(cwd)

    def test_total_output_respects_the_hard_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, "q" * (state.WORKING_STATE_BUDGET * 5))
            # A large dirty tree would otherwise blow the git section up.
            for i in range(400):
                (cwd / f"file-with-a-fairly-long-name-{i}.txt").write_text("x")
            context = self._recovery(cwd)
            self.assertLessEqual(len(context), state.TOTAL_BUDGET)

    def test_oversized_state_is_marked_and_points_at_the_full_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, "w" * (state.WORKING_STATE_BUDGET * 2))
            context = self._recovery(cwd)
            self.assertIn(state.TRUNCATION_MARKER, context)
            self.assertIn("WORKING_STATE.md", context)

    def test_recovery_context_states_the_filesystem_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            context = self._recovery(cwd)
            self.assertIn("source of truth", context)
            self.assertIn("Scaffold context-guard v0.1.", context)

    def test_missing_state_does_not_invent_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            context = self._recovery(cwd)
            self.assertLessEqual(len(context), state.TOTAL_BUDGET)
            self.assertNotIn("# Decisions", context)
            self.assertNotIn("# Acceptance criteria", context)


class TestGitSectionBudget(unittest.TestCase):
    def test_git_section_is_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            for i in range(500):
                (cwd / f"untracked-{i}.txt").write_text("x")
            rendered = git_state.render(git_state.collect(cwd))
            self.assertLessEqual(len(rendered), state.GIT_BUDGET)

    def test_non_git_directory_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = git_state.collect(Path(tmp))
            self.assertFalse(info["is_repo"])
            self.assertIsInstance(git_state.render(info), str)


if __name__ == "__main__":
    unittest.main()
