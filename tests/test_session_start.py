"""SessionStart(compact) is the only path that rehydrates, and it must stay inside budget."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import SAMPLE_STATE, init_git_repo, load_fixture, run_cli, write_working_state

from context_guard import hooks, state, storage


def additional_context(output: dict) -> str | None:
    return (output or {}).get("hookSpecificOutput", {}).get("additionalContext")


class TestSessionStartCompact(unittest.TestCase):
    def test_compact_source_injects_recovery_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            output = hooks.handle_session_start(payload)

            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
            context = additional_context(output)
            self.assertIn("Scaffold context-guard v0.1.", context)
            self.assertIn("work", context)  # current branch, recomputed
            self.assertLessEqual(len(context), state.TOTAL_BUDGET)

    def test_output_is_valid_json_on_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            result = run_cli("session-start", json.dumps(payload))

            self.assertEqual(result.returncode, 0)
            parsed = json.loads(result.stdout)
            self.assertEqual(parsed["hookSpecificOutput"]["hookEventName"], "SessionStart")
            self.assertIn("additionalContext", parsed["hookSpecificOutput"])

    def test_rehydration_is_recorded_as_an_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            hooks.handle_session_start(payload)

            events_path = storage.session_dir(cwd, payload["session_id"]) / "events.jsonl"
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual([e["event"] for e in events], ["rehydrate"])
            self.assertEqual(events[0]["source"], "compact")


class TestSessionStartOtherSources(unittest.TestCase):
    def test_non_compact_sources_inject_nothing(self):
        for source in ("startup", "resume", "clear", "fork"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                cwd = Path(tmp)
                write_working_state(cwd, SAMPLE_STATE)
                payload = load_fixture("session_start_compact.json", cwd=str(cwd), source=source)

                output = hooks.handle_session_start(payload)

                self.assertIsNone(additional_context(output))

    def test_missing_source_injects_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))
            payload.pop("source")

            self.assertIsNone(additional_context(hooks.handle_session_start(payload)))

    def test_unknown_future_source_injects_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd), source="teleport")

            self.assertIsNone(additional_context(hooks.handle_session_start(payload)))


class TestSessionStartDegraded(unittest.TestCase):
    def test_missing_working_state_injects_only_a_minimal_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            context = additional_context(hooks.handle_session_start(payload))

            self.assertIsNotNone(context)
            self.assertIn("source of truth", context)
            self.assertNotIn("# Decisions", context)
            self.assertLessEqual(len(context), state.TOTAL_BUDGET)

    def test_oversized_state_is_truncated_within_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, SAMPLE_STATE + "p" * 40000)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            context = additional_context(hooks.handle_session_start(payload))

            self.assertLessEqual(len(context), state.TOTAL_BUDGET)
            self.assertIn(state.TRUNCATION_MARKER, context)
            self.assertIn("WORKING_STATE.md", context)

    def test_non_git_project_still_rehydrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            context = additional_context(hooks.handle_session_start(payload))

            self.assertIn("Scaffold context-guard v0.1.", context)

    def test_malformed_json_exits_zero_without_injecting(self):
        result = run_cli("session-start", "}{")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("additionalContext", result.stdout)

    def test_undecodable_working_state_still_injects_recovery_context(self):
        # Total silence is worse than a garbled state: without the recovery
        # instruction Claude has no signal that compaction just happened.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            target = cwd / ".claude" / "context-guard" / "WORKING_STATE.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"# Goal\n\n\xff\xfe broken bytes\n")
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            context = additional_context(hooks.handle_session_start(payload))

            self.assertIsNotNone(context)
            self.assertIn("source of truth", context)
            self.assertLessEqual(len(context), state.TOTAL_BUDGET)

    def test_rehydration_survives_an_unwritable_event_log(self):
        # Observability must never be able to kill the feature it observes.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            sessions = storage.guard_root(cwd) / "sessions"
            sessions.write_text("a regular file where the sessions dir should be")
            payload = load_fixture("session_start_compact.json", cwd=str(cwd))

            context = additional_context(hooks.handle_session_start(payload))

            self.assertIsNotNone(context)
            self.assertIn("Scaffold context-guard v0.1.", context)

    def test_post_compact_summary_is_not_reinjected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            post = load_fixture("post_compact.json", cwd=str(cwd))
            hooks.handle_post_compact(post)

            payload = load_fixture("session_start_compact.json", cwd=str(cwd))
            context = additional_context(hooks.handle_session_start(payload))

            self.assertNotIn("Investigation is complete", context)


if __name__ == "__main__":
    unittest.main()
