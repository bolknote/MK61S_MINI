#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import check_stack_usage as stack_usage


class StackUsageSelfTest(unittest.TestCase):
    def test_parses_static_and_bounded_dynamic_records(self) -> None:
        report = Path("unit.su")
        static = stack_usage.parse_line(
            report, 1, "/src/a.cpp:1:1:void a()\t4904\tstatic"
        )
        bounded = stack_usage.parse_line(
            report, 2, "/src/b.cpp:2:1:void b()\t128\tdynamic,bounded"
        )
        self.assertEqual(static.bytes, 4904)
        self.assertFalse(static.unbounded)
        self.assertFalse(bounded.unbounded)
        self.assertEqual(stack_usage.policy_failures(
            [static, bounded], stack_usage.DEFAULT_MAX_FRAME
        ), [])

    def test_rejects_unbounded_dynamic_and_oversized_frames(self) -> None:
        report = Path("unit.su")
        dynamic = stack_usage.parse_line(
            report, 1, "/src/a.cpp:1:1:void a()\t64\tdynamic"
        )
        large = stack_usage.parse_line(
            report, 2, "/src/b.cpp:2:1:void b()\t5121\tstatic"
        )
        failures = stack_usage.policy_failures([dynamic, large], 5120)
        self.assertTrue(any("unbounded" in failure for failure in failures))
        self.assertTrue(any("exceeds" in failure for failure in failures))

    def test_rejects_unknown_or_malformed_records(self) -> None:
        report = Path("unit.su")
        with self.assertRaisesRegex(stack_usage.StackUsageError, "malformed"):
            stack_usage.parse_line(report, 1, "not-a-report")
        with self.assertRaisesRegex(stack_usage.StackUsageError, "qualifier"):
            stack_usage.parse_line(report, 2, "fn\t8\tmystery")
        with self.assertRaisesRegex(stack_usage.StackUsageError, "byte count"):
            stack_usage.parse_line(report, 3, "fn\tlarge\tstatic")

    def test_requires_nonempty_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(stack_usage.StackUsageError, "no .su"):
                stack_usage.read_records(root)
            (root / "empty.su").write_text("", encoding="utf-8")
            with self.assertRaisesRegex(stack_usage.StackUsageError, "empty"):
                stack_usage.read_records(root)
            (root / "one.su").write_text(
                "file.cpp:1:1:void ok()\t32\tstatic\n", encoding="utf-8"
            )
            reports, records = stack_usage.read_records(root)
            self.assertEqual(len(reports), 2)
            self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
