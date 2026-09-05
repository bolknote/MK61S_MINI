"""Exercise the actual shell gate with a minimal tool PATH, including failures."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


GATE = Path(__file__).resolve().with_name("check_keyboard_handoff.sh")
BASH = shutil.which("bash")
GREP = shutil.which("grep")
LEGACY_NAMES = (
    "exclude_before",
    "drop_pending_key_events",
    "drop_menu_exit_key_events",
    "drop_key_events_until_release",
)


class KeyboardSourceGateTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(BASH, "bash is required")
        self.assertIsNotNone(GREP, "grep is required")
        temporary = tempfile.TemporaryDirectory(prefix="mk61-keyboard-gate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "code"
        self.source.mkdir()
        (self.source / "keyboard.cpp").write_text("void handoff();\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "grep").symlink_to(GREP)

    def run_gate(self, source=None):
        return subprocess.run(
            [BASH, str(GATE), str(self.source if source is None else source)],
            env={**os.environ, "PATH": str(self.bin), "LC_ALL": "C"},
            text=True, capture_output=True, check=False,
        )

    def test_clean_source_passes_without_ripgrep(self):
        self.assertIsNone(shutil.which("rg", path=str(self.bin)))
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_each_legacy_name_is_rejected_in_nested_source(self):
        nested = self.source / "nested"
        nested.mkdir()
        for name in LEGACY_NAMES:
            with self.subTest(name=name):
                (nested / "consumer.cpp").write_text(f"void {name}();\n")
                result = self.run_gate()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(name, result.stdout)
                self.assertIn("must not coexist", result.stderr)

    def test_missing_source_is_not_a_pass(self):
        result = self.run_gate(self.root / "missing")
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_missing_grep_is_not_a_pass(self):
        (self.bin / "grep").unlink()
        result = self.run_gate()
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn("source scan failed", result.stderr)

    def test_read_error_after_a_match_is_reported_as_scan_failure(self):
        (self.bin / "grep").unlink()
        grep = self.bin / "grep"
        grep.write_text(
            f"#!{BASH}\n"
            "printf 'consumer.cpp:1:exclude_before\\n'\n"
            "exit 2\n"
        )
        grep.chmod(0o755)
        result = self.run_gate()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("source scan failed", result.stderr)
        self.assertNotIn("must not coexist", result.stderr)


if __name__ == "__main__":
    unittest.main()
