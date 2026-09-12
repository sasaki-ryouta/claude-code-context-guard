"""Fail-open invariants (SPEC 2.4) and runtime purity (SPEC 3, 9)."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

from _support import REPO_ROOT, SRC_DIR, load_fixture, run_cli, write_working_state

HOOK_COMMANDS = ("pre-compact", "session-start", "post-compact")
BLOCKING_MARKERS = ('"decision"', '"continue": false', '"continue":false', '"stopReason"')


class TestHookNeverBlocks(unittest.TestCase):
    def test_every_hook_exits_zero_on_garbage_input(self):
        garbage = ("", "   ", "{not json", "[]", '"a string"', "null", "42", "\x00\x01")
        for command in HOOK_COMMANDS:
            for payload in garbage:
                with self.subTest(command=command, payload=repr(payload)):
                    result = run_cli(command, payload)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_pathological_json_does_not_escape_as_an_exception(self):
        # A recursive decoder blows the stack long before it blows memory;
        # the traceback would surface as a non-zero exit and block compaction.
        pathological = ("[" * 100000) + ("]" * 100000)
        for command in HOOK_COMMANDS:
            with self.subTest(command=command):
                result = run_cli(command, pathological)
                self.assertEqual(result.returncode, 0, result.stderr[-400:])
                self.assertEqual(result.stderr.strip(), "")

    def test_no_hook_ever_emits_a_blocking_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            write_working_state(cwd, "# Goal\n\nsomething\n")
            payloads = {
                "pre-compact": load_fixture("pre_compact.json", cwd=str(cwd)),
                "session-start": load_fixture("session_start_compact.json", cwd=str(cwd)),
                "post-compact": load_fixture("post_compact.json", cwd=str(cwd)),
            }
            for command, payload in payloads.items():
                with self.subTest(command=command):
                    result = run_cli(command, json.dumps(payload))
                    self.assertEqual(result.returncode, 0)
                    for marker in BLOCKING_MARKERS:
                        self.assertNotIn(marker, result.stdout)
                    if result.stdout.strip():
                        json.loads(result.stdout)

    def test_unwritable_guard_root_does_not_break_compaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            # A regular file where the guard directory should be: every write must fail.
            (cwd / ".claude").mkdir()
            (cwd / ".claude" / "context-guard").write_text("not a directory")
            for command, fixture in (
                ("pre-compact", "pre_compact.json"),
                ("session-start", "session_start_compact.json"),
                ("post-compact", "post_compact.json"),
            ):
                with self.subTest(command=command):
                    payload = load_fixture(fixture, cwd=str(cwd))
                    result = run_cli(command, json.dumps(payload))
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_nonexistent_cwd_does_not_break_compaction(self):
        payload = load_fixture("pre_compact.json", cwd="/nonexistent/path/xyzzy")
        self.assertEqual(run_cli("pre-compact", json.dumps(payload)).returncode, 0)

    def test_unknown_subcommand_still_exits_zero(self):
        # A stale settings.json entry must not turn into a blocked compaction.
        self.assertEqual(run_cli("pre-compaction-typo", "{}").returncode, 0)


class TestHarnessIsolation(unittest.TestCase):
    def test_the_suite_never_writes_into_this_repository(self):
        # Hooks fall back to the process cwd when the payload omits one
        # (SPEC 2.4). If the harness inherits the developer's cwd, that
        # fallback lands in this repository and pollutes real runtime state
        # — it did exactly that during the live smoke test on 2026-09-12.
        payload = {"session_id": "harness-isolation-probe", "trigger": "manual"}
        result = run_cli("pre-compact", json.dumps(payload))

        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        leaked = REPO_ROOT / ".claude" / "context-guard" / "sessions" / "harness-isolation-probe"
        self.assertFalse(leaked.exists(), f"the test harness wrote into the repository: {leaked}")


class TestNoWritesOutsideGuardRoot(unittest.TestCase):
    def test_hooks_only_touch_the_guard_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp) / "project"
            cwd.mkdir()
            (cwd / "app.py").write_text("print('hi')\n")
            before = {p: p.stat().st_mtime_ns for p in cwd.rglob("*") if p.is_file()}
            outside = Path(tmp) / "outside.txt"
            outside.write_text("untouched")

            for command, fixture in (
                ("pre-compact", "pre_compact.json"),
                ("session-start", "session_start_compact.json"),
                ("post-compact", "post_compact.json"),
            ):
                payload = load_fixture(fixture, cwd=str(cwd))
                run_cli(command, json.dumps(payload))

            self.assertEqual(outside.read_text(), "untouched")
            guard_root = (cwd / ".claude" / "context-guard").resolve()
            for path in cwd.rglob("*"):
                if not path.is_file():
                    continue
                if path in before:
                    self.assertEqual(before[path], path.stat().st_mtime_ns)
                else:
                    self.assertTrue(path.resolve().is_relative_to(guard_root))


class TestRuntimePurity(unittest.TestCase):
    def _runtime_modules(self) -> set[str]:
        modules: set[str] = set()
        for source_file in sorted(SRC_DIR.rglob("*.py")):
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules.add(node.module.split(".")[0])
        return modules

    def test_runtime_imports_only_the_standard_library(self):
        third_party = {
            name
            for name in self._runtime_modules()
            if name not in sys.stdlib_module_names and name != "context_guard"
        }
        self.assertEqual(third_party, set())

    def test_runtime_does_not_import_network_or_database_modules(self):
        forbidden = {
            "socket",
            "ssl",
            "http",
            "urllib",
            "urllib2",
            "ftplib",
            "smtplib",
            "telnetlib",
            "sqlite3",
            "asyncio",
            "xmlrpc",
        }
        self.assertEqual(self._runtime_modules() & forbidden, set())

    def test_runtime_declares_no_dependencies(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("dependencies = []", pyproject)

    def test_runtime_never_uses_shell_execution(self):
        for source_file in sorted(SRC_DIR.rglob("*.py")):
            text = source_file.read_text(encoding="utf-8")
            with self.subTest(file=source_file.name):
                self.assertNotIn("shell=True", text)
                self.assertNotIn("os.system", text)
                self.assertNotIn("os.popen", text)

    def test_runtime_never_reads_the_transcript_body(self):
        for source_file in sorted(SRC_DIR.rglob("*.py")):
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in {"read_text", "read_bytes", "open"}:
                    # The transcript path is only ever recorded, never opened.
                    segment = ast.unparse(node)
                    self.assertNotIn("transcript", segment.lower())


if __name__ == "__main__":
    unittest.main()
