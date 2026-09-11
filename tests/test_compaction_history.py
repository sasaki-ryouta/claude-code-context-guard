"""Every compaction keeps immutable provenance for later benchmark scoring."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import SAMPLE_STATE, load_fixture, write_working_state
from context_guard import hooks, storage


def _events(root: Path, session_id: str) -> list[dict]:
    path = storage.session_dir(root, session_id) / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestCompactionHistory(unittest.TestCase):
    def test_two_compactions_produce_two_archived_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_working_state(root, SAMPLE_STATE)
            session_id = "history-session"
            for index in (1, 2):
                pre = load_fixture("pre_compact.json", cwd=str(root), session_id=session_id, trigger="manual")
                post = load_fixture("post_compact.json", cwd=str(root), session_id=session_id, trigger="manual", compact_summary=f"summary {index}")
                hooks.handle_pre_compact(pre)
                hooks.handle_post_compact(post)
            first = storage.compaction_dir(root, session_id, 1)
            second = storage.compaction_dir(root, session_id, 2)
            self.assertEqual(json.loads((first / "checkpoint.json").read_text(encoding="utf-8"))["compaction_sequence"], 1)
            self.assertEqual((first / "compact-summary.md").read_text(encoding="utf-8"), "summary 1")
            self.assertEqual((second / "compact-summary.md").read_text(encoding="utf-8"), "summary 2")
            session = storage.session_dir(root, session_id)
            self.assertEqual((session / "compact-summary.md").read_text(encoding="utf-8"), "summary 2")
            self.assertEqual(json.loads((session / "checkpoint.json").read_text(encoding="utf-8"))["compaction_sequence"], 2)
            sequence_events = [event["compaction_sequence"] for event in _events(root, session_id) if event["event"] in {"pre_compact", "post_compact"}]
            self.assertEqual(sequence_events, [1, 1, 2, 2])

    def test_postcompact_without_precompact_degrades_without_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = load_fixture("post_compact.json", cwd=str(root), session_id="orphan-post", compact_summary="orphan summary")
            hooks.handle_post_compact(payload)
            session = storage.session_dir(root, payload["session_id"])
            self.assertEqual((session / "compact-summary.md").read_text(encoding="utf-8"), "orphan summary")
            self.assertIsNone(_events(root, payload["session_id"])[0]["compaction_sequence"])
            self.assertFalse((session / "compactions").exists())


if __name__ == "__main__":
    unittest.main()
