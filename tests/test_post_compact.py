"""PostCompact persists the native summary verbatim and records its metadata."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _support import load_fixture, run_cli

from context_guard import hooks, storage


def events(cwd: Path, session_id: str) -> list[dict]:
    path = storage.session_dir(cwd, session_id) / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestPostCompactPersistence(unittest.TestCase):
    def test_summary_is_saved_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = load_fixture("post_compact.json", cwd=str(cwd))

            hooks.handle_post_compact(payload)

            saved = (storage.session_dir(cwd, payload["session_id"]) / "compact-summary.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(saved, payload["compact_summary"])

    def test_metadata_and_hash_are_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = load_fixture("post_compact.json", cwd=str(cwd))
            summary = payload["compact_summary"]

            hooks.handle_post_compact(payload)

            event = events(cwd, payload["session_id"])[0]
            self.assertEqual(event["event"], "post_compact")
            self.assertEqual(event["trigger"], "auto")
            self.assertEqual(event["summary_chars"], len(summary))
            self.assertEqual(
                event["summary_sha256"], hashlib.sha256(summary.encode("utf-8")).hexdigest()
            )
            self.assertTrue(event["timestamp"].endswith("Z"))

    def test_summary_is_not_returned_to_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = load_fixture("post_compact.json", cwd=str(cwd))

            result = run_cli("post-compact", json.dumps(payload))

            self.assertEqual(result.returncode, 0)
            self.assertNotIn("additionalContext", result.stdout)
            self.assertNotIn("Investigation is complete", result.stdout)

    def test_repeated_compactions_append_events_and_keep_the_latest_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            first = load_fixture("post_compact.json", cwd=str(cwd), compact_summary="first summary")
            second = load_fixture("post_compact.json", cwd=str(cwd), compact_summary="second summary")

            hooks.handle_post_compact(first)
            hooks.handle_post_compact(second)

            session = storage.session_dir(cwd, first["session_id"])
            self.assertEqual(
                (session / "compact-summary.md").read_text(encoding="utf-8"), "second summary"
            )
            self.assertEqual(len(events(cwd, first["session_id"])), 2)


class TestPostCompactDegraded(unittest.TestCase):
    def test_missing_summary_is_handled_without_writing_a_summary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = load_fixture("post_compact.json", cwd=str(cwd))
            payload.pop("compact_summary")

            hooks.handle_post_compact(payload)

            session = storage.session_dir(cwd, payload["session_id"])
            self.assertFalse((session / "compact-summary.md").exists())
            event = events(cwd, payload["session_id"])[0]
            self.assertEqual(event["summary_chars"], 0)
            self.assertIsNone(event["summary_sha256"])

    def test_null_summary_is_handled_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = load_fixture("post_compact.json", cwd=str(cwd), compact_summary=None)

            hooks.handle_post_compact(payload)

            self.assertEqual(events(cwd, payload["session_id"])[0]["summary_chars"], 0)

    def test_malformed_json_exits_zero(self):
        self.assertEqual(run_cli("post-compact", "nope").returncode, 0)

    def test_traversal_session_id_stays_inside_the_guard_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp) / "project"
            cwd.mkdir()
            payload = load_fixture(
                "post_compact.json", cwd=str(cwd), session_id="../../../../tmp/pwned"
            )

            hooks.handle_post_compact(payload)

            self.assertFalse((Path(tmp) / "pwned").exists())
            guard_root = storage.guard_root(cwd).resolve()
            for path in cwd.rglob("*"):
                if path.is_file():
                    self.assertTrue(path.resolve().is_relative_to(guard_root))


if __name__ == "__main__":
    unittest.main()
