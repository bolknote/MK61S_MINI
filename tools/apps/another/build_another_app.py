#!/usr/bin/env python3
"""Build the Another World interpreter without distributing game data."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.firmware.picocalc.build_picocalc import compiler_bin

SOURCES = ["main.c", "assets.c", "prepared.c", "video.c", "display.c", "display_compact.c", "vm.c", "audio.c", "text.c",
           "rp2040_divide.S"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".build/another-app")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".build/game-library/sd/apps/ANOTHER")
    args = parser.parse_args()
    src = ROOT / "examples/portable-apps/ANOTHER"
    command = [sys.executable, str(ROOT / "tools/apps/portable/build_portable_app.py"),
               "--target", "picocalc-pico-h", "--shared-runtime", "--name", "ANOTHER",
               "--arm-toolchain-bin", str(compiler_bin(args.toolchain)), "--output-dir", str(args.build_dir)]
    for name in SOURCES:
        command += ["--source", str(src / name)]
    subprocess.run(command, check=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.build_dir / "ANOTHER.APP", args.output_dir / "ANOTHER.APP")
    shutil.copy2(src / "README.md", args.output_dir / "README.md")
    shutil.copy2(ROOT / "LICENSE", args.output_dir / "COPYING.txt")
    shutil.copy2(ROOT / "third_party/rp2040-softfloat/LICENSE.TXT", args.output_dir / "RP2040-LICENSE.txt")
    report = json.loads((args.build_dir / "ANOTHER.json").read_text())
    report["app_sha256"] = hashlib.sha256((args.output_dir / "ANOTHER.APP").read_bytes()).hexdigest()
    report["game_data_included"] = False
    report["hardware_verified"] = False
    (args.build_dir / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Another World APP: " + str(args.output_dir / "ANOTHER.APP"))


if __name__ == "__main__":
    main()
