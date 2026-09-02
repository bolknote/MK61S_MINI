#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import analyze_stack_usage as analysis


class AnalyzeStackUsageSelfTest(unittest.TestCase):
    def test_rewrites_lto_command_without_touching_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.cpp"
            entry = {
                "directory": str(root),
                "file": str(source),
                "arguments": [
                    "/tool/g++", "-DMODE=1", "-Os", "-flto",
                    "-fstack-usage", "-MMD", "-MF", "old.d", "-c",
                    str(source), "-o", "old.o",
                ],
            }
            output = root / "analysis.o"
            arguments, cwd = analysis.analysis_arguments(entry, output)
            self.assertEqual(cwd, root)
            self.assertIn("-DMODE=1", arguments)
            self.assertIn("-fno-lto", arguments)
            self.assertIn("-fstack-usage", arguments)
            self.assertNotIn("-flto", arguments)
            self.assertNotIn("old.d", arguments)
            self.assertNotIn("old.o", arguments)
            self.assertEqual(arguments[-1], str(output))
            self.assertEqual(Path(arguments[-3]).resolve(), source.resolve())

    def test_selects_exact_sources_and_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "code"
            code.mkdir()
            inside = code / "inside.cpp"
            exact = root / "exact.cpp"
            outside = root / "outside.cpp"
            entries = [
                {"directory": str(root), "file": str(path),
                 "arguments": ["g++", "-c", str(path)]}
                for path in (inside, exact, outside)
            ]
            selected = analysis.selected_entries(entries, [code], [exact])
            self.assertEqual(
                {Path(entry["file"]) for entry in selected}, {inside, exact}
            )


if __name__ == "__main__":
    unittest.main()
