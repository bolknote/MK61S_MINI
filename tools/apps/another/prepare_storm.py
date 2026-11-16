#!/usr/bin/env python3
"""Prepare the optional intro cache from an existing local DOS data folder."""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "examples/portable-apps/ANOTHER"
ZX0 = ROOT / "tools/apps/packer/third_party/zx0"


def prepare(directory: Path) -> Path | None:
    if not (directory / "MEMLIST.BIN").is_file():
        return None
    compiler = shlex.split(os.environ.get("CC", "cc"))
    with tempfile.TemporaryDirectory(prefix="another-storm-") as work:
        helper = Path(work) / "prepare-storm"
        command = [*compiler, "-std=c11", "-O2", "-I", str(APP), "-I", str(ZX0),
                   str(Path(__file__).with_suffix(".c")),
                   *(str(APP / f"{unit}.c") for unit in (
                       "assets", "video", "vm", "text", "audio", "display_compact", "display_pages")),
                   *(str(ZX0 / f"{unit}.c") for unit in ("compress", "optimize", "memory")),
                   "-o", str(helper)]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError):
            print("AWSTORM.BIN unavailable: the native cache builder could not be compiled.")
            return None
        target = directory / "AWSTORM.BIN"
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".awstorm-", delete=False) as file:
            temporary = Path(file.name)
        try:
            result = subprocess.run([helper, directory, temporary], stdout=subprocess.DEVNULL)
            if result.returncode == 2:
                return None
            result.check_returncode()
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"Prepared AWSTORM.BIN: {target.stat().st_size} bytes")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    prepare(parser.parse_args().directory)
