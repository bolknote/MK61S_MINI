#!/usr/bin/env python3
"""Keep the host dictionary in lockstep with stable firmware error numbers."""
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/vfat_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("vfat_diagnostic", TOOL)
assert SPEC and SPEC.loader
DIAGNOSTIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGNOSTIC)


class DiagnosticToolTest(unittest.TestCase):
    def test_every_firmware_code_has_one_explanation(self):
        header = (ROOT / "code/virtual_fat_diagnostic.hpp").read_text()
        enum = header.split("enum class ErrorCode : u16 {", 1)[1].split("};", 1)[0]
        values = [int(value) for value in re.findall(r"=\s*(\d+)", enum)]
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(set(values), set(DIAGNOSTIC.MESSAGES))
        for value in values:
            self.assertTrue(DIAGNOSTIC.describe(value))
        self.assertEqual(DIAGNOSTIC.describe(1299), "Unknown VFAT error")

    def test_cli_accepts_transcript_or_argument_without_interpreting_prose(self):
        record = ("VFAT v=1 code=1221 phase=3 flags=0 actual=7492 "
                  "limit=1536 subject=524541444D45")
        expected = record + "\nFile too large\n"
        for args, transcript in (([record], None), ([], "vlog\n" + record + "\n/> ")):
            result = subprocess.run([sys.executable, str(TOOL), *args],
                                    input=transcript, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)
        result = subprocess.run([sys.executable, str(TOOL), record.replace("v=1", "v=2")],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("File too large", result.stdout)


if __name__ == "__main__":
    unittest.main()
