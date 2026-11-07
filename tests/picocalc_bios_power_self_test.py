#!/usr/bin/env python3
"""Execute the production Southbridge PMU reader with a bounded HAL fixture."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="mk61-bios-power-") as work:
    binary = Path(work) / "power-test"
    flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.environ.get("MK61_TEST_SANITIZERS") == "1" else []
    subprocess.run(["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", *flags,
        "-I" + str(ROOT / "tests/fixtures/picocalc_bios_power_hal"),
        "-I" + str(ROOT / "ports/picocalc/bios"),
        str(ROOT / "ports/picocalc/bios/power_status.c"),
        str(ROOT / "tests/picocalc_bios_power_self_test.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
