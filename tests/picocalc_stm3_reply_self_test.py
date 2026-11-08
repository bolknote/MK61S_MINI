#!/usr/bin/env python3
"""Run archived coproc_poll and the real STM3 runtime with a UART DMA model."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools/firmware/picocalc")]
from spectrum_m3_runtime_fixture import prepare
from bios_stm3_reply import stage_stm3_reply


def main():
    with tempfile.TemporaryDirectory(prefix="mk61-stm3-reply-") as folder:
        work = Path(folder)
        prepare(work)
        baseline = ROOT / "firmware/picocalc-southbridge"
        manifest = json.loads((baseline / "manifest.json").read_text())
        member = "source/Core/Src/coproc_hal.c"
        with zipfile.ZipFile(baseline / "source.zip") as archive:
            data = archive.read(member)
        assert hashlib.sha256(data).hexdigest() == manifest["source_archive_files"][member]
        path = work / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        legacy = path.read_text()
        stage_stm3_reply(work / "source")
        current = path.read_text()
        # Execute both versions: the baseline must demonstrate the extra
        # foreground turn, while the staged production version must remove it.
        for name, text in [("legacy", legacy), ("current", current)]:
            poll = text[text.index("void coproc_poll(void){"):text.index("void coproc_enter_sleep(void){")]
            (work / (name + ".inc")).write_text(poll)
        flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                 "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
        subprocess.run(["clang", "-std=c11", *flags, "-Wno-misleading-indentation", "-I" + str(work),
                        "-c", str(work / "stm3_runtime.c"), "-o", str(work / "runtime.o")], check=True)
        for name in ["legacy", "current"]:
            binary = work / name
            subprocess.run(["clang++", "-std=c++17", *flags, "-I" + str(work),
                            "-I" + str(ROOT / "ports/picocalc"), '-DPOLL_FILE="' + name + '.inc"',
                            "-DEXPECT_IMMEDIATE=" + str(int(name == "current")),
                            str(ROOT / "tests/picocalc_stm3_reply_self_test.cpp"),
                            str(work / "runtime.o"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
