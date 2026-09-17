#!/usr/bin/env python3
"""Build the public-domain 3x5 ASCII face used by the High Noon game."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "code/ERM19264_graphics_font.cpp"
DEFAULT_OUTPUT = ROOT / "programs/Fonts/HighNoon.FMK"
HEADER_SIZE = 16


class BitWriter:
    def __init__(self, prefix: bytes) -> None:
        self.data = bytearray(prefix)
        self.position = len(prefix) * 8

    def write(self, value: int, count: int) -> None:
        for bit in range(count - 1, -1, -1):
            byte = self.position // 8
            if byte == len(self.data):
                self.data.append(0)
            if value & (1 << bit):
                self.data[byte] |= 0x80 >> (self.position & 7)
            self.position += 1


def put_le16(data: bytearray, offset: int, value: int) -> None:
    data[offset] = value & 0xFF
    data[offset + 1] = (value >> 8) & 0xFF


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for index, byte in enumerate(data):
        if index in (14, 15):
            byte = 0
        crc ^= byte << 8
        for _ in range(8):
            crc = (((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def source_rows() -> list[int]:
    text = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"static const unsigned char UC_Font_3x5\[\].*?=\s*\{(.*?)\n\};",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("UC_Font_3x5 source array not found")
    initializer = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)
    initializer = re.sub(r"//.*", "", initializer)
    values = [int(token, 16) for token in re.findall(r"0x[0-9A-Fa-f]+", initializer)]
    if len(values) != 128 * 5 or any(value & ~0x07 for value in values):
        raise ValueError("unexpected UC_Font_3x5 source layout")
    return values


def encode() -> bytes:
    rows = source_rows()
    first = 0x20
    last = 0x7E
    glyph_count = last - first + 1
    prefix = bytearray(HEADER_SIZE)
    prefix[:4] = b"FMK1"
    prefix[4] = 1       # monospaced
    prefix[5] = 3       # bitmap width
    prefix[6] = 5       # bitmap height
    prefix[7] = 0x31    # four-pixel advance, one-pixel line gap
    put_le16(prefix, 8, glyph_count)
    prefix[10] = 1
    prefix += bytes((first, 0, glyph_count - 1))

    writer = BitWriter(prefix)
    for codepoint in range(first, last + 1):
        writer.write(0, 1)  # raw bitmap
        for row in rows[codepoint * 5:(codepoint + 1) * 5]:
            # The resident table numbers its leftmost pixel as bit zero.
            for x in range(3):
                writer.write((row >> x) & 1, 1)

    put_le16(writer.data, 12, len(writer.data))
    put_le16(writer.data, 14, crc16(writer.data))
    return bytes(writer.data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = encode()
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            raise SystemExit(f"{args.output}: generated HighNoon FMK differs")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(expected)
    print(f"{args.output}: {len(expected)} bytes, 95 glyphs, mono 3x5")


if __name__ == "__main__":
    main()
