#!/usr/bin/env python3
"""Old Windows Arduino hooks must not enter the retired Python build path."""
import importlib.util
from pathlib import Path
import sys
from unittest import TestCase, main, mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PythonBuildHostTests(TestCase):
    def test_windows_stops_before_reading_build_inputs_or_starting_tools(self):
        for name, replacement in (
                ("build_portable_app", "build-portable-app.ps1"),
                ("build_system_app_bundle", "build-system-app-bundle.ps1")):
            with self.subTest(builder=name):
                module = load(name)
                with mock.patch.object(module.sys, "platform", "win32"), \
                        mock.patch.object(module.subprocess, "run") as run:
                    with self.assertRaises(ValueError) as error:
                        module.build(None)
                    message = str(error.exception)
                    self.assertIn(replacement, message)
                    self.assertIn("tools/mk61-arduino-board.cmd", message)
                    self.assertIn("restart Arduino IDE", message)
                    run.assert_not_called()


if __name__ == "__main__":
    main()
