#!/usr/bin/env python3
"""Reject accidental reads from an installed Arduino/STM32duino package."""
import argparse
import json
from pathlib import Path
import re
from analyze_stack_usage import entry_arguments
import subprocess

FORBIDDEN = re.compile(r"(?:^|/)(?:arduino15|\.arduino15|cores/arduino|libraries/srcwrapper)(?:/|$)", re.I)


def check_paths(paths):
    bad = [str(p) for p in paths if FORBIDDEN.search(str(p).replace("\\", "/"))]
    if bad:
        raise ValueError("Installed Arduino package entered native build: " + ", ".join(bad[:5]))


def check(database, dependencies=True):
    entries = json.loads(Path(database).read_text())
    assert entries, "compile database is empty"
    sdk = None
    for entry in entries:
        args = entry_arguments(entry)
        check_paths([entry["file"], *args])
        includes = [Path(v[2:]) for v in args if v.startswith("-I")]
        candidates = [p.parent.parent for p in includes if p.as_posix().endswith("/cmsis/include")]
        assert len(candidates) == 1, "native CMSIS include root is missing or ambiguous"
        if sdk is None:
            sdk = candidates[0]
        assert candidates[0] == sdk, "translation units use different SDKs"
        assert (sdk / "manifest.json").is_file(), "native SDK manifest missing"
        assert not any("CMSIS_DSP" in str(v) for v in includes), "unused external DSP path returned"
    if dependencies:
        text = subprocess.check_output(["ninja", "-C", str(Path(database).resolve().parent), "-t", "deps"], text=True)
        headers = [v.strip() for v in text.splitlines() if v.startswith(" ")]
        assert headers, "Ninja header dependencies are missing"
        check_paths(headers)
    return sdk


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print("Independent native SDK and header dependency gate PASS:", check(args.database))
