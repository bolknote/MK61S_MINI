#!/usr/bin/env python3
"""Build a relocatable PicoCalc MP3 player and its SD card files."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.apps.mp3.pack_requant import pack
from tools.firmware.picocalc.build_picocalc import compiler_bin

APP = ROOT / "examples/portable-apps/MP3"
MAD = ROOT / "third_party/libmad"
MAD_SOURCES = ("bit", "fixed", "frame", "huffman", "layer3", "stream", "synth", "timer")
SD_FILES = ("MP3.APP", "RECORD.LP", "CASSETTE.TV", "REEL.TV", "README.md",
            "LIBMAD-LICENSE.txt", "RP2040-LICENSE.txt")


def build(toolchain: Path, work: Path, output: Path, packer: Path | None) -> None:
    work.mkdir(parents=True, exist_ok=True)
    pack(MAD / "rq_table.dat", work / "rq_compact.h")
    objects = []
    for name in MAD_SOURCES:
        obj = work / (name + ".mad.o")
        subprocess.run([str(toolchain / "arm-none-eabi-gcc"), "-mcpu=cortex-m0plus", "-mthumb",
                        "-mfloat-abi=soft", "-Os", "-std=c11", "-fwrapv",
                        "-ffreestanding", "-fno-builtin", "-mword-relocations",
                        "-ffunction-sections", "-fdata-sections", "-DNDEBUG", "-DMK61_MAD_APP",
                        "-Wno-stringop-overflow", "-I" + str(work), "-c", str(MAD / (name + ".c")),
                        "-o", str(obj)], check=True)
        objects.append(obj)
    lib = work / "libmad-app.a"
    subprocess.run([str(toolchain / "arm-none-eabi-ar"), "rcs", str(lib), *map(str, objects)], check=True)
    command = [sys.executable, str(ROOT / "tools/apps/portable/build_portable_app.py"),
               "--target", "picocalc-pico-h", "--name", "MP3",
               "--arm-toolchain-bin", str(toolchain), "--output-dir", str(work),
               "--handled-magic", "A3", "--optimize-size", "--shared-runtime", "--include", str(MAD),
               "--library", str(lib)]
    for name in ("main.cpp", "metadata.cpp", "audio.cpp", "screen.cpp", "tape.cpp"):
        command.extend(["--source", str(APP / name)])
    command.extend(["--source", str(ROOT / "sdk/portable/rp2040_divide.S")])
    if packer:
        command.extend(["--packer", str(packer)])
    subprocess.run(command, check=True, cwd=ROOT)

    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(work / "MP3.APP", output / "MP3.APP")
    for name in ("RECORD.LP", "CASSETTE.TV", "REEL.TV", "README.md"):
        shutil.copy2(APP / name, output / name)
    shutil.copy2(MAD / "COPYING", output / "LIBMAD-LICENSE.txt")
    shutil.copy2(ROOT / "third_party/rp2040-softfloat/LICENSE.TXT", output / "RP2040-LICENSE.txt")
    report = json.loads((work / "MP3.json").read_bytes())
    report["files"] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in SD_FILES}
    report["app_sha256"] = report["files"]["MP3.APP"]
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{output}: {report['memory_bytes']} bytes in the loaded APP, {report['app_bytes']} on SD")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--packer", type=Path)
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".build/mp3-app")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/firmware/picocalc-pico-h/apps/MP3")
    args = parser.parse_args()
    build(compiler_bin(args.toolchain), args.build_dir.resolve(), args.output_dir.resolve(), args.packer)


if __name__ == "__main__":
    main()
