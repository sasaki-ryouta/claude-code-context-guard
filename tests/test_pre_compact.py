"""PreCompact must checkpoint deterministically and never interfere with compaction."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _support import SAMPLE_STATE, init_git_repo, load_fixture, run_cli, write_working_state

from context_guard import hooks, storage


def read_events(cwd: Path, session_id: str) -> list[dict]:
    path = storage.session_dir(cwd, session_id) / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestPreCompactHappyPath(unittest.TestCase):
    def test_manual_trigger_writes_a_complete_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("pre_compact.json", cwd=str(cwd))

            hooks.handle_pre_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            checkpoint = json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))

            self.assertEqual(checkpoint["event"], "pre_compact")
            self.assertEqual(checkpoint["trigger"], "manual")
            self.assertEqual(checkpoint["session_id"], "fixture-session-0001")
            self.assertTrue(checkpoint["timestamp"].endswith("Z"))
            self.assertEqual(checkpoint["git"]["branch"], "work")
            self.assertEqual(len(checkpoint["git"]["head"]), 40)
            self.assertTrue(checkpoint["working_state"]["exists"])
            self.assertEqual(checkpoint["working_state"]["chars"], len(SAMPLE_STATE))
            self.assertEqual(
                checkpoint["working_state"]["sha256"],
                hashlib.sha256(SAMPLE_STATE.encode("utf-8")).hexdigest(),
            )
            self.assertTrue((session / "checkpoint.md").exists())
            self.assertEqual([e["event"] for e in read_events(cwd, payload["session_id"])], ["pre_compact"])

    def test_auto_trigger_is_recorded_as_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("pre_compact.json", cwd=str(cwd), trigger="auto")

            hooks.handle_pre_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            checkpoint = json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["trigger"], "auto")
            self.assertEqual(read_events(cwd, payload["session_id"])[0]["trigger"], "auto")

    def test_checkpoint_stores_the_working_state_snapshot(self):
        # SPEC 7.1 captures the snapshot itself, not only its hash: the
        # checkpoint is what lets a later run see what the state looked like
        # at compaction time. WORKING_STATE is curated prose, not code or logs.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("pre_compact.json", cwd=str(cwd))

            hooks.handle_pre_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            checkpoint = json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["working_state"]["snapshot"], SAMPLE_STATE)
            self.assertIn("Scaffold context-guard v0.1.", (session / "checkpoint.md").read_text(encoding="utf-8"))

    def test_missing_working_state_has_no_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = load_fixture("pre_compact.json", cwd=str(cwd))

            hooks.handle_pre_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            checkpoint = json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertIsNone(checkpoint["working_state"]["snapshot"])

    def test_checkpoint_does_not_store_transcript_or_diff_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            write_working_state(cwd, SAMPLE_STATE)
            (cwd / "tracked.txt").write_text("secret-diff-body\n")
            transcript = cwd / "transcript.jsonl"
            transcript.write_text('{"role":"user","content":"transcript body must not be copied"}\n')
            payload = load_fixture("pre_compact.json", cwd=str(cwd), transcript_path=str(transcript))

            hooks.handle_pre_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            blob = (session / "checkpoint.json").read_text(encoding="utf-8") + (
                session / "checkpoint.md"
            ).read_text(encoding="utf-8")
            self.assertNotIn("transcript body must not be copied", blob)
            self.assertNotIn("secret-diff-body", blob)
            # The pointer itself is fine; the body is not.
            self.assertIn("transcript.jsonl", blob)

    def test_working_state_is_never_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            state_path = write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("pre_compact.json", cwd=str(cwd))

            hooks.handle_pre_compact(payload)

            self.assertEqual(state_path.read_text(encoding="utf-8"), SAMPLE_STATE)

    def test_hook_emits_no_context_back_to_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("pre_compact.json", cwd=str(cwd))

            result = run_cli("pre-compact", json.dumps(payload))

            self.assertEqual(result.returncode, 0)
            self.assertNotIn("additionalContext", result.stdout)


class TestPreCompactDegradedInputs(unittest.TestCase):
    def test_missing_working_state_still_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            init_git_repo(cwd)
            payload = load_fixture("pre_compact.json", cwd=str(cwd))

            hooks.handle_pre_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            checkpoint = json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertFalse(checkpoint["working_state"]["exists"])
            self.assertIsNone(checkpoint["working_state"]["sha256"])

    def test_non_git_directory_still_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, SAMPLE_STATE)
            payload = load_fixture("pre_compact.json", cwd=str(cwd))

            hooks.handle_pre_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            checkpoint = json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertFalse(checkpoint["git"]["is_repo"])
            self.assertIsNone(checkpoint["git"]["branch"])

    def test_malformed_json_exits_zero(self):
        result = run_cli("pre-compact", "{not json at all")
        self.assertEqual(result.returncode, 0)

    def test_missing_cwd_falls_back_to_process_cwd_without_crashing(self):
        payload = load_fixture("pre_compact.json")
        payload.pop("cwd")
        result = run_cli("pre-compact", json.dumps(payload))
        self.assertEqual(result.returncode, 0)


class TestPreCompactPathSafety(unittest.TestCase):
    def test_traversal_session_id_stays_inside_the_guard_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp) / "project"
            cwd.mkdir()
            canary = Path(tmp) / "escaped"
            payload = load_fixture(
                "pre_compact.json", cwd=str(cwd), session_id="../../escaped/../../../etc/passwd"
            )

            hooks.handle_pre_compact(payload)

            self.assertFalse(canary.exists())
            written = sorted(p for p in cwd.rglob("*") if p.is_file())
            self.assertTrue(written, "expected the checkpoint to be written somewhere")
            guard_root = storage.guard_root(cwd).resolve()
            for path in written:
                self.assertTrue(path.resolve().is_relative_to(guard_root))

    def test_absolute_session_id_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp) / "project"
            cwd.mkdir()
            payload = load_fixture("pre_compact.json", cwd=str(cwd), session_id="/etc/passwd")

            hooks.handle_pre_compact(payload)

            guard_root = storage.guard_root(cwd).resolve()
            for path in cwd.rglob("*"):
                if path.is_file():
                    self.assertTrue(path.resolve().is_relative_to(guard_root))

    def test_empty_session_id_is_replaced_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = load_fixture("pre_compact.json", cwd=str(cwd), session_id="")

            hooks.handle_pre_compact(payload)

            sessions = storage.guard_root(cwd) / "sessions"
            self.assertTrue(any(p.is_dir() for p in sessions.iterdir()))


if __name__ == "__main__":
    unittest.main()
