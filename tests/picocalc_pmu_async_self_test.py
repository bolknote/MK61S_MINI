#!/usr/bin/env python3
"""Exercise the actual async driver plus archived legacy AXP/button code."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/firmware/picocalc"))
from bios_pmu_async import stage_async_pmu


def prepare_fixture(work):
    staged = work / "source"
    baseline = ROOT / "firmware/picocalc-southbridge"
    archive_path = baseline / "source.zip"
    manifest = json.loads((baseline / "manifest.json").read_text())
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == manifest["source_archive_sha256"]
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if name.startswith("source/Core/") and not name.endswith("/"):
                assert ".." not in Path(name).parts
                out = work / name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(archive.read(name))
    stage_async_pmu(staged)
    mock = work / "mock"
    shutil.copytree(ROOT / "tests/fixtures/picocalc_pmu_async_hal", mock)
    for name in ["regs.h", "axp2101.h", "keyboard.h", "batt.h"]:
        shutil.copyfile(staged / "Core/Inc" / name, mock / name)
    main = (staged / "Core/Src/main.c").read_text()
    start = main.index("__STATIC_INLINE void check_pmu_int(void) {")
    end = main.index("__STATIC_INLINE void rtc_ctrl_reg_check(void) {", start)
    (mock / "legacy_check.inc").write_text(main[start:end])
    return staged, mock


def run_host(work):
    staged, mock = prepare_fixture(work)
    binary = work / "test"
    flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.environ.get("MK61_TEST_SANITIZERS") == "1" else []
    subprocess.run(["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", *flags,
        "-I" + str(mock), "-I" + str(ROOT / "ports/picocalc/bios"),
        str(ROOT / "ports/picocalc/bios/pmu_async.c"), str(staged / "Core/Src/axp2101.c"),
        str(staged / "Core/Src/batt.c"), str(ROOT / "tests/picocalc_pmu_async_self_test.c"), "-o", str(binary)], check=True)
    for case in ["normal", "wrap", "offline"]:
        subprocess.run([str(binary), case], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mk61-pmu-async-") as directory:
        work = Path(directory)
        run_host(work)
        if args.keep:
            if args.keep.exists():
                raise ValueError("--keep must name a new directory")
            shutil.copytree(work, args.keep)
