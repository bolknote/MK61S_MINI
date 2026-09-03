#!/usr/bin/env python3

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import analyze_stack_usage as analysis


def windows_api_fixture(arguments: list[str] | None):
    """Exercise real ctypes pointer marshalling without requiring Windows."""
    values = (
        (ctypes.c_wchar_p * len(arguments))(*arguments)
        if arguments is not None else None
    )
    calls = {"commands": [], "freed": []}

    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_wchar_p,
                     ctypes.POINTER(ctypes.c_int))
    def parse(command, count):
        calls["commands"].append(command)
        count[0] = len(arguments) if arguments is not None else 0
        return ctypes.addressof(values) if values is not None else None

    @ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)
    def free(address):
        calls["freed"].append(address)
        return None

    # Unbound DLL functions default to int results. A plain Python mock would
    # hide the lost pointer that broke the Windows post-link stack analysis.
    for function in (parse, free):
        function.argtypes = None
        function.restype = ctypes.c_int
    api = SimpleNamespace(
        shell32=SimpleNamespace(CommandLineToArgvW=parse),
        kernel32=SimpleNamespace(LocalFree=free),
    )
    return api, calls, values


class AnalyzeStackUsageSelfTest(unittest.TestCase):
    def test_windows_api_preserves_and_frees_full_pointer(self) -> None:
        expected = [r"C:\Program Files\Arm GCC\g++.exe", "-c",
                    r"C:\Проект с пробелами\source.cpp", '-DTEXT="hello world"']
        command = subprocess.list2cmdline(expected)
        api, calls, values = windows_api_fixture(expected)
        with patch.object(analysis.ctypes, "windll", api, create=True), \
             patch.object(analysis.os, "name", "nt"):
            self.assertEqual(analysis.entry_arguments({"command": command}), expected)
        self.assertEqual(calls["commands"], [command])
        self.assertEqual(calls["freed"], [ctypes.addressof(values)])
        self.assertEqual(api.shell32.CommandLineToArgvW.argtypes,
                         [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)])
        self.assertIs(api.shell32.CommandLineToArgvW.restype,
                      ctypes.POINTER(ctypes.c_wchar_p))
        self.assertEqual(api.kernel32.LocalFree.argtypes, [ctypes.c_void_p])
        self.assertIs(api.kernel32.LocalFree.restype, ctypes.c_void_p)

    def test_windows_api_failure_is_not_dereferenced_or_freed(self) -> None:
        api, calls, _values = windows_api_fixture(None)
        with patch.object(analysis.ctypes, "windll", api, create=True):
            with self.assertRaisesRegex(OSError, "CommandLineToArgvW failed"):
                analysis.windows_command_line("g++ -c source.cpp")
        self.assertEqual(calls["commands"], ["g++ -c source.cpp"])
        self.assertEqual(calls["freed"], [])

    def test_explicit_arguments_bypass_windows_parser(self) -> None:
        expected = [r"C:\Program Files\Arm GCC\g++.exe", "-c", "source.cpp"]
        with patch.object(analysis, "windows_command_line") as parse, \
             patch.object(analysis.os, "name", "nt"):
            result = analysis.entry_arguments({"arguments": expected,
                                               "command": "must not be parsed"})
        parse.assert_not_called()
        self.assertEqual(result, expected)
        self.assertIsNot(result, expected)

    @unittest.skipUnless(os.name == "nt", "requires the real Windows shell32 API")
    def test_native_windows_command_line_round_trip(self) -> None:
        expected = [
            r"C:\Program Files\Arm GCC\arm-none-eabi-g++.exe",
            r"-IC:\Проект с пробелами\include", '-DTEXT="hello world"',
            "", "C:\\trailing slash\\", r'escaped\"quote',
            "-c", r"C:\Проект с пробелами\source.cpp",
            "-o", r"C:\build dir\source.cpp.obj",
        ]
        self.assertEqual(
            analysis.entry_arguments({"command": subprocess.list2cmdline(expected)}),
            expected,
        )

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
