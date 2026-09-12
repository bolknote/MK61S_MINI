#!/usr/bin/env python3
"""Pack a reviewed native bitmap atlas into a proportional FMK1 file.

The atlas format is emitted by tools/.fmk-font/font_preview.cpp. Bearings are
baked into the FMK bitmap because FMK1 deliberately keeps its on-device glyph
record to width, advance and pixels only. No scaling or hinting happens here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

HEADER_SIZE = 16
MAX_FILE_SIZE = 8192


class BitWriter:
    def __init__(self, prefix: bytes) -> None:
        self.data = bytearray(prefix)
        self.position = len(self.data) * 8

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
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def ranges(codepoints: Iterable[int]) -> list[tuple[int, int]]:
    values = list(codepoints)
    if not values:
        raise ValueError("atlas contains no glyphs")
    result: list[tuple[int, int]] = []
    start = previous = values[0]
    count = 1
    for codepoint in values[1:]:
        if codepoint == previous + 1 and count < 256:
            count += 1
        else:
            result.append((start, count))
            start, count = codepoint, 1
        previous = codepoint
    result.append((start, count))
    if len(result) > 255:
        raise ValueError("FMK1 supports at most 255 codepoint ranges")
    return result


def glyph_canvas(glyph: dict, ascent: int, font_height: int) -> tuple[int, int, list[int]]:
    source_width = int(glyph["width"])
    source_height = int(glyph["height"])
    left = int(glyph["safe_bearing_x"])
    top = ascent - int(glyph["bearing_y"])
    advance = int(glyph["advance"])
    rows = glyph["rows"]
    if source_width < 1 or source_height < 1 or len(rows) != source_height:
        raise ValueError(f"invalid glyph geometry for U+{int(glyph['codepoint']):04X}")
    if left < 0 or top < 0 or top + source_height > font_height:
        raise ValueError(f"glyph U+{int(glyph['codepoint']):04X} escapes the line envelope")
    width = max(1, left + source_width)
    if width > 16 or advance < width or advance > 16:
        raise ValueError(f"glyph U+{int(glyph['codepoint']):04X} exceeds FMK1 metrics")
    pixels = [0] * (width * font_height)
    for y, row in enumerate(rows):
        if len(row) != source_width or any(pixel not in "01" for pixel in row):
            raise ValueError(f"invalid bitmap row for U+{int(glyph['codepoint']):04X}")
        for x, pixel in enumerate(row):
            if pixel == "1":
                pixels[(top + y) * width + left + x] = 1
    return width, advance, pixels


def encode(atlas: dict, line_gap: int) -> bytes:
    if atlas.get("schema") != 1:
        raise ValueError("unsupported atlas schema")
    height = int(atlas["height"])
    ascent = int(atlas["ascent"])
    descent = int(atlas["descent"])
    if height not in (12, 14, 16) or ascent + descent != height:
        raise ValueError("external UI atlas height must be 12, 14 or 16")
    if line_gap < 0 or line_gap > 4 or (64 + line_gap) // (height + line_gap) < 3:
        raise ValueError("line gap does not leave three UC1609 rows")

    source = sorted(atlas["glyphs"], key=lambda glyph: int(glyph["codepoint"]))
    codepoints = [int(glyph["codepoint"]) for glyph in source]
    if len(codepoints) != len(set(codepoints)) or any(cp < 0 or cp > 0xFFFF for cp in codepoints):
        raise ValueError("glyph codepoints must be unique Unicode BMP values")
    if ord(" ") not in codepoints or ord("?") not in codepoints:
        raise ValueError("UI FMK requires space and question-mark glyphs")

    prepared = []
    max_width = max_advance = 0
    for glyph in source:
        width, advance, pixels = glyph_canvas(glyph, ascent, height)
        prepared.append((width, advance, pixels))
        max_width = max(max_width, width)
        max_advance = max(max_advance, advance)

    groups = ranges(codepoints)
    prefix = bytearray(HEADER_SIZE)
    prefix[:4] = b"FMK1"
    prefix[4] = 0  # proportional
    prefix[5] = max_width
    prefix[6] = height
    prefix[7] = ((max_advance - 1) << 4) | line_gap
    put_le16(prefix, 8, len(prepared))
    prefix[10] = len(groups)
    for start, count in groups:
        prefix += bytes((start & 0xFF, start >> 8, count - 1))

    writer = BitWriter(prefix)
    for width, advance, pixels in prepared:
        writer.write(width - 1, 4)
        writer.write(advance - 1, 4)
        writer.write(0, 1)  # raw bitmap: reviewed pixels stay bit-exact
        for pixel in pixels:
            writer.write(pixel, 1)

    if len(writer.data) > MAX_FILE_SIZE:
        raise ValueError(f"encoded FMK is {len(writer.data)} bytes; maximum is {MAX_FILE_SIZE}")
    put_le16(writer.data, 12, len(writer.data))
    put_le16(writer.data, 14, crc16(writer.data))
    return bytes(writer.data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--line-gap", type=int)
    parser.add_argument("--check", action="store_true", help="compare with an existing output")
    args = parser.parse_args()

    atlas = json.loads(args.atlas.read_text(encoding="utf-8"))
    height = int(atlas["height"])
    line_gap = args.line_gap if args.line_gap is not None else (1 if height == 12 else 2)
    encoded = encode(atlas, line_gap)
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != encoded:
            raise SystemExit(f"{args.output}: generated FMK differs")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    print(f"{args.output}: {len(encoded)} bytes, {len(atlas['glyphs'])} glyphs, "
          f"proportional {atlas['height']}px, source={atlas.get('family', '?')}")


if __name__ == "__main__":
    main()
