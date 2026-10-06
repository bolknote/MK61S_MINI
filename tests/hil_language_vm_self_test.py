#!/usr/bin/env python3
"""Offline gates for the language HIL harness; no device is opened."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from hil_language_vm import EXTENDED_FIXTURES, FIXTURES, require_foreground

ROOT=Path(__file__).resolve().parents[1]


class ForegroundSafety(unittest.TestCase):
    def test_failed_open_stops_before_keys(self):
        for text in (b'open "x"\r\nOpen failed!\r\n/> ',b'open "x"\r\n/> '):
            with self.subTest(text=text),self.assertRaises(AssertionError):
                require_foreground(SimpleNamespace(text=text,open_text_start=0))

    def test_only_current_open_is_checked(self):
        old=b'old failed open\r\nOpen failed!\r\n/> '
        text=old+b'open "x"\r\n'
        require_foreground(SimpleNamespace(text=text,open_text_start=len(old)))


class FixtureBytecode(unittest.TestCase):
    def test_compile_and_large_staging_bound(self):
        compiler=shutil.which("clang++") or shutil.which("c++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="mk61-hil-language-") as work:
            directory=Path(work);probe=directory/"probe"
            subprocess.run([compiler,"-std=c++17","-O2","-I"+str(ROOT/"code"),
                str(ROOT/"tools/language_vm_probe.cpp"),
                str(ROOT/"code/language_bytecode.cpp"),str(ROOT/"code/language_vm.cpp"),
                str(ROOT/"code/zx0_encode.cpp"),"-o",str(probe)],check=True)
            for name,data in {**FIXTURES,**EXTENDED_FIXTURES}.items():
                if name.endswith(".m61"):continue
                with self.subTest(name=name):
                    source=directory/name;source.write_bytes(data)
                    output=directory/(name+".bvm")
                    language="basic" if name.endswith(".tbi") else "focal"
                    result=subprocess.run([str(probe),language,str(source),str(output)],
                                          check=True,capture_output=True,text=True)
                    sizes=json.loads(result.stdout)
                    if name=="large.tbi":
                        self.assertLessEqual(sizes["source_bytes"],3584)
                        self.assertGreater(sizes["bytecode_bytes"],3184)
                        self.assertLessEqual(sizes["bytecode_bytes"],6144)


if __name__=="__main__":unittest.main()
