#!/usr/bin/env python3
"""Validate the exact large-source hardware fixtures without opening a board."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from hil_language_sources import fixture

ROOT = Path(__file__).resolve().parents[1]


class SourceFixtures(unittest.TestCase):
    def test_real_compilers_and_large_resource_offsets(self):
        compiler = shutil.which("clang++") or shutil.which("c++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="mk61-hil-sources-") as work:
            directory = Path(work)
            probe = directory / "probe"
            subprocess.run([compiler, "-std=c++17", "-O2", "-I" + str(ROOT / "code"),
                str(ROOT / "tools/language_vm_probe.cpp"),
                str(ROOT / "code/language_bytecode.cpp"),
                str(ROOT / "code/language_vm.cpp"), str(ROOT / "code/zx0_encode.cpp"),
                "-o", str(probe)], check=True)
            for language in ("basic", "focal"):
                for size, resources in ((3585, False), (16384, False),
                                        (32768, False), (65534, False), (65534, True)):
                    with self.subTest(language=language, size=size, resources=resources):
                        data = fixture(language, size, resources)
                        source = directory / "source"
                        source.write_bytes(data)
                        image = directory / "image"
                        result = subprocess.run([str(probe), language, str(source),
                            str(image), "--source-resources" if resources else "--owned-resources"],
                            capture_output=True, text=True, check=True)
                        sizes = json.loads(result.stdout)
                        self.assertEqual(sizes["source_bytes"], size)
                        self.assertLess(sizes["bytecode_bytes"], 1024)
                        if resources:
                            body = image.read_bytes()
                            at = sizes["code_bytes"]
                            offsets = []
                            while at < len(body):
                                spans = body[at + 2]
                                for i in range(spans):
                                    offset = at + 3 + i * 3
                                    if body[offset + 2]:
                                        offsets.append(int.from_bytes(body[offset:offset + 2], "little"))
                                at += 3 + 3 * spans
                            self.assertEqual(at, len(body))
                            self.assertTrue(any(offset > 32767 for offset in offsets))
                            failed = subprocess.run([str(probe), language, str(source),
                                str(image), "--owned-resources"], capture_output=True)
                            self.assertEqual(failed.returncode, 1)


if __name__ == "__main__":
    unittest.main()
