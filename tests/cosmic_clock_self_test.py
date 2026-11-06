#!/usr/bin/env python3
"""Check clock transitions, reset ordering and I2C recovery without hardware."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="picocalc-cosmic-clock-") as temp:
    binary = Path(temp) / "clock-test"
    command = ["clang++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
               "-I" + str(ROOT / "ports/picocalc")]
    if os.environ.get("MK61_TEST_SANITIZERS") == "1":
        command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    subprocess.run(command + [str(ROOT / "tests/cosmic_clock_self_test.cpp"),
                              "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
