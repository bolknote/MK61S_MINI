#!/usr/bin/env python3
"""Minimal objcopy stand-in for the resident ELF sealer host test."""

from pathlib import Path
import sys


if len(sys.argv) != 5 or sys.argv[1:3] != ["-O", "binary"]:
    raise SystemExit(2)

source = Path(sys.argv[3]).read_bytes()
if source[:8] != b"FAKEELF\0" or len(source) != 64 + 512 + 32:
    raise SystemExit(3)
Path(sys.argv[4]).write_bytes(source[64:64 + 512])
