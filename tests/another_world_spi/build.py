#!/usr/bin/env python3
"""Build the two RP2040 storm probes and optionally replay the scene on the host."""

import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from tools.apps.another.build_another_app import SOURCES
from tools.firmware.picocalc.build_picocalc import compiler_bin

GAME = ROOT / "examples/portable-apps/ANOTHER"
UNITS = [HERE / "main.c" if name == "main.c" else GAME / name for name in SOURCES]
PROBES = {"AWSCOPE": [], "AWFEED": ["AW_DMA_FEED"]}


def build_arm(output, toolchain):
    for name, defines in PROBES.items():
        command = [
            sys.executable, ROOT / "tools/apps/portable/build_portable_app.py",
            "--target", "picocalc-pico-h", "--shared-runtime", "--name", name,
            "--arm-toolchain-bin", toolchain, "--output-dir", output / name,
            "--include", GAME, "--include", output,
        ]
        for define in defines:
            command.extend(["--define", define])
        for source in [ROOT / "code/zx0.cpp", ROOT / "sdk/portable/rp2040_divide.S", *UNITS]:
            command.extend(["--source", source])
        subprocess.run(command, check=True)


def check_host(output, game_data):
    feeder_test = output / "test-feed"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", HERE / "test_feed.c", "-o", feeder_test],
                   check=True)
    subprocess.run([feeder_test], check=True)
    # The two probes share the same VM, renderer and synchronous mock LCD.
    flags = ["-O2", "-g", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
             "-fno-sanitize-recover=all", "-I", GAME, "-I", ROOT / "sdk/portable/include", "-I", ROOT / "code"]
    cpp_objects = []
    for src in [GAME / "display_storm.cpp", ROOT / "code/zx0.cpp"]:
        obj = output / (src.stem + ".o")
        subprocess.run(["c++", "-std=c++17", "-fno-exceptions", *flags, "-c", src, "-o", obj], check=True)
        cpp_objects.append(obj)
    for name, defines in PROBES.items():
        obj = output / (name + ".o")
        exe = output / (name + "-host")
        subprocess.run(["cc", "-std=c11", *flags, "-DAW_TRACE_HOST", "-Dmain=another_app_main",
                        *["-D" + define for define in defines], "-c", HERE / "main.c", "-o", obj], check=True)
        sources = [src for src in UNITS if src.name not in {"main.c", "display_storm.cpp"}]
        subprocess.run(["cc", "-std=c11", *flags, "-DAW_TRACE_HOST", "-DAW_TEST_LCD_READBACK",
                        ROOT / "tests/another_world_app_host_test.c", *sources, obj, *cpp_objects, "-o", exe],
                       check=True)
        with (output / (name + "-host.txt")).open("w") as log:
            subprocess.run([exe, game_data, "profile-pages"], stdout=log, check=True)
        print(f"{name}: 67 displayed frames match the live VM")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pioasm", default="pioasm", help="Pico SDK pioasm executable")
    parser.add_argument("--toolchain", type=Path, help="Arm GNU toolchain bin directory")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/another-world-spi")
    parser.add_argument("--check-data", type=Path, help="replay the probes with an installed DOS game directory")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    header = output / "wire.pio.h"
    subprocess.run([args.pioasm, "-v", "0", "-o", "c-sdk", HERE / "wire.pio", header], check=True)
    subprocess.run([sys.executable, HERE / "test_pio.py", header], check=True)
    build_arm(output, compiler_bin(args.toolchain))
    if args.check_data:
        check_host(output, args.check_data.resolve())


if __name__ == "__main__":
    main()
