#!/usr/bin/env python3
"""Exercise the actual CMake Flash gate, including native Windows paths."""

import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = ROOT / "tools" / ".mk61-gcc" / "check-flash.cmake"


class FlashBudgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmake = shutil.which("cmake")
        if cls.cmake is None:
            raise RuntimeError("Flash budget tests require cmake")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mk61 flash ")
        self.addCleanup(self.temporary.cleanup)
        self.image = pathlib.Path(self.temporary.name) / "resident image.bin"

    def check(self, size=3584, capacity="4096", headroom="512"):
        if size is not None:
            self.image.write_bytes(bytes(size))
        return subprocess.run(
            [
                self.cmake,
                f"-DMK61_BIN={self.image}",
                f"-DMK61_FLASH_CAPACITY={capacity}",
                f"-DMK61_FLASH_MIN_HEADROOM={headroom}",
                "-P", str(CHECK),
            ],
            capture_output=True, text=True, check=False,
        )

    def test_exact_headroom_is_accepted(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("image 3584/4096, free 512", result.stdout)

    def test_one_byte_over_budget_is_rejected(self):
        result = self.check(size=3585)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Flash headroom below budget", result.stderr)
        self.assertIn("511 bytes available", result.stderr)

    def test_physical_overflow_is_rejected(self):
        result = self.check(size=4097)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("-1 bytes available", result.stderr)

    def test_missing_or_empty_image_is_rejected(self):
        for size in (None, 0):
            with self.subTest(size=size):
                result = self.check(size=size)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("MK61_BIN", result.stderr)

    def test_directory_is_not_an_image(self):
        self.image.mkdir()
        result = self.check(size=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a file", result.stderr)

    def test_invalid_capacity_is_rejected(self):
        for capacity in ("", "0", "-1", "4K", "4096oops"):
            with self.subTest(capacity=capacity):
                result = self.check(capacity=capacity)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("MK61_FLASH_CAPACITY", result.stderr)

    def test_invalid_headroom_is_rejected(self):
        for headroom in ("", "-1", "512oops", "4097"):
            with self.subTest(headroom=headroom):
                result = self.check(headroom=headroom)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("MK61_FLASH_MIN_HEADROOM", result.stderr)


if __name__ == "__main__":
    unittest.main()
