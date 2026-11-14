#!/usr/bin/env python3
"""Prepare an optional local sound cache from a user's DOS game files."""
# ByteKiller format based on Raw, Copyright (C) 2004 Gregory Montoir,
# GPL-2.0-or-later.

from __future__ import annotations

import argparse
from pathlib import Path
import os
import struct
import tempfile


def fnv(data: bytes) -> int:
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def unpack(data: bytes, size: int) -> bytes:
    if len(data) == size:
        return data
    if len(data) < 12 or len(data) % 4:
        raise ValueError("Invalid ByteKiller input size")

    def word(at: int) -> int:
        if at < 0 or at + 4 > len(data):
            raise ValueError("Truncated ByteKiller input")
        return int.from_bytes(data[at : at + 4], "big")

    if word(len(data) - 4) != size:
        raise ValueError("ByteKiller output size mismatch")
    cursor = len(data) - 12
    bits = word(cursor)
    crc = word(len(data) - 8) ^ bits
    output = bytearray(size)
    remaining = size

    def bit() -> int:
        nonlocal bits, cursor, crc
        result = bits & 1
        bits >>= 1
        if not bits:
            if cursor < 4:
                raise ValueError("Truncated ByteKiller bitstream")
            cursor -= 4
            bits = word(cursor)
            crc ^= bits
            result = bits & 1
            bits = (bits >> 1) | 0x80000000
        return result

    def field(count: int) -> int:
        value = 0
        for _ in range(count):
            value = (value << 1) | bit()
        return value

    def literal(count: int) -> None:
        nonlocal remaining
        if count > remaining:
            raise ValueError("Invalid ByteKiller literal")
        for _ in range(count):
            remaining -= 1
            output[remaining] = field(8)

    def backref(count: int, distance: int) -> None:
        nonlocal remaining
        if count > remaining or not distance or distance > size - remaining:
            raise ValueError("Invalid ByteKiller reference")
        for _ in range(count):
            remaining -= 1
            output[remaining] = output[remaining + distance]

    while remaining:
        if not bit():
            if not bit():
                literal(field(3) + 1)
            else:
                backref(2, field(8))
        else:
            code = field(2)
            if code == 3:
                literal(field(8) + 9)
            elif code < 2:
                backref(code + 3, field(code + 9))
            else:
                count = field(8) + 1
                backref(count, field(12))
    if crc:
        raise ValueError("ByteKiller checksum mismatch")
    return bytes(output)


def prepare(directory: Path) -> tuple[int, int]:
    listing = (directory / "MEMLIST.BIN").read_bytes()
    if not listing or len(listing) > 4096:
        raise ValueError("Invalid MEMLIST.BIN size")
    entries = []
    for at in range(0, len(listing), 20):
        if listing[at] == 0xFF:
            break
        if len(listing) - at < 20 or len(entries) >= 150:
            raise ValueError("Invalid MEMLIST.BIN entries")
        entries.append(listing[at : at + 20])
    else:
        raise ValueError("Missing MEMLIST.BIN terminator")
    if not entries:
        raise ValueError("Empty MEMLIST.BIN")
    payload = bytearray()
    records = bytearray(len(entries) * 12)
    banks: dict[int, bytes] = {}
    sound_count = 0
    for index, entry in enumerate(entries):
        kind, bank = entry[1], entry[7]
        offset = int.from_bytes(entry[8:12], "big")
        packed = int.from_bytes(entry[14:16], "big")
        size = int.from_bytes(entry[18:20], "big")
        if packed > size or offset + packed > 0xFFFFFFFF:
            raise ValueError(f"Invalid resource {index}")
        if kind or not bank or not packed or not size:
            continue
        if bank not in banks:
            banks[bank] = (directory / f"BANK{bank:02X}").read_bytes()
        source = banks[bank][offset : offset + packed]
        if len(source) != packed:
            raise ValueError(f"Truncated BANK{bank:02X} resource {index}")
        raw = unpack(source, size)
        start = 24 + len(records) + len(payload)
        struct.pack_into("<III", records, index * 12, start, fnv(source), fnv(raw))
        payload.extend(raw)
        sound_count += 1
    header = struct.pack("<4sIIIII", b"AWC1", 1, len(entries), len(listing), fnv(listing), len(records))
    destination = directory / "AWCACHE.BIN"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".awcache-", delete=False) as file:
            temporary = Path(file.name)
            file.write(header)
            file.write(records)
            file.write(payload)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return sound_count, len(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="folder containing MEMLIST.BIN and BANK files")
    args = parser.parse_args()
    try:
        count, size = prepare(args.directory)
    except (OSError, ValueError) as error:
        parser.exit(1, f"another-cache: {error}\n")
    print(f"Prepared AWCACHE.BIN: {count} sounds, {size} decoded bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
