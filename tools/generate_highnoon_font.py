#!/usr/bin/env python3
"""Build the compact proportional Russian face used by High Noon."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "code/ERM19264_graphics_font.cpp"
DEFAULT_OUTPUT = ROOT / "programs/games/High Noon/HighNoon.FMK"
HEADER_SIZE = 16


def art(*rows: str) -> tuple[int, list[int]]:
    """Convert a readable left-to-right bitmap into the resident row format."""
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("inconsistent glyph art")
    width = len(rows[0])
    if len(rows) != 5 or width < 1 or width > 5:
        raise ValueError("High Noon glyphs must be 1..5 by 5 pixels")
    encoded: list[int] = []
    for row in rows:
        if any(pixel not in ".#" for pixel in row):
            raise ValueError("glyph art accepts only '.' and '#'")
        encoded.append(sum(1 << x for x, pixel in enumerate(row)
                           if pixel == "#"))
    return width, encoded


# Three columns are enough for most capitals, but not for letters whose
# identity depends on several vertical strokes or a diagonal.  These hand
# fitted forms keep the ten-row game layout while making Russian words read as
# Russian instead of look-alike Latin/garbled text.
WIDE_GLYPHS: dict[int, tuple[int, list[int]]] = {
    ord("Д"): art("..#..", ".#.#.", ".#.#.", "#####", "#...#"),
    ord("Ж"): art("#.#.#", "#.#.#", ".###.", "#.#.#", "#.#.#"),
    ord("И"): art("#...#", "#..##", "#.#.#", "##..#", "#...#"),
    ord("Й"): art(".#.#.", "#...#", "#..##", "#.#.#", "##..#"),
    ord("Л"): art("..#..", ".#.#.", ".#.#.", "#...#", "#...#"),
    ord("М"): art("#...#", "##.##", "#.#.#", "#...#", "#...#"),
    ord("Ф"): art("..#..", ".###.", "#.#.#", ".###.", "..#.."),
    ord("Ш"): art("#.#.#", "#.#.#", "#.#.#", "#.#.#", "#####"),
    ord("Щ"): art("#.#.#", "#.#.#", "#.#.#", "#####", "....#"),
    ord("Ы"): art("#...#", "#...#", "###.#", "#.#.#", "###.#"),
    ord("Ю"): art("#.###", "#.#.#", "###.#", "#.#.#", "#.###"),
    ord("Я"): art(".####", "#...#", ".####", "..#.#", ".#..#"),
}


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


def source_glyphs() -> dict[int, list[int]]:
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
    glyphs = {
        codepoint: values[codepoint * 5:(codepoint + 1) * 5]
        for codepoint in range(128)
    }

    extra = re.search(
        r"static const Font3x5Glyph UC_Font_3x5_Extra\[\].*?=\s*\{"
        r"(.*?)\n\};",
        text,
        flags=re.DOTALL,
    )
    if not extra:
        raise ValueError("UC_Font_3x5_Extra source array not found")
    entries = re.findall(
        r"\{\s*(0x[0-9A-Fa-f]+)\s*,\s*\{([^}]*)\}\s*\}",
        extra.group(1),
    )
    for encoded_codepoint, encoded_rows in entries:
        codepoint = int(encoded_codepoint, 16)
        rows = [int(token, 16) for token in re.findall(
            r"0x[0-9A-Fa-f]+", encoded_rows
        )]
        if len(rows) != 5 or any(value & ~0x07 for value in rows):
            raise ValueError(f"invalid 3x5 glyph U+{codepoint:04X}")
        glyphs[codepoint] = rows
    return glyphs


def encode() -> bytes:
    glyphs = source_glyphs()
    if glyphs.get(0x0401) == glyphs.get(0x0415):
        raise ValueError("Russian 3x5 Ё must be distinguishable from Е")
    # The translated game renders uppercase Russian only.  Keep the ASCII
    # punctuation/digits needed by its UI, Ё, and А..Я; carrying Latin letters
    # in this local face would just spend disk/BULK space on unreachable art.
    ranges = ((0x20, 0x20), (0x0401, 1), (0x0410, 0x20))
    codepoints = [
        codepoint
        for first, count in ranges
        for codepoint in range(first, first + count)
    ]
    missing = [codepoint for codepoint in codepoints if codepoint not in glyphs]
    if missing:
        raise ValueError(f"missing source glyph U+{missing[0]:04X}")
    glyph_count = len(codepoints)
    prefix = bytearray(HEADER_SIZE)
    prefix[:4] = b"FMK1"
    prefix[4] = 0       # proportional: individual width and advance follow
    prefix[5] = 5       # maximum bitmap width
    prefix[6] = 5       # bitmap height
    prefix[7] = 0x31    # nominal four-pixel advance, one-pixel line gap
    put_le16(prefix, 8, glyph_count)
    prefix[10] = len(ranges)
    for first, count in ranges:
        prefix += bytes((first & 0xFF, first >> 8, count - 1))

    writer = BitWriter(prefix)
    for codepoint in codepoints:
        width, rows = WIDE_GLYPHS.get(codepoint, (3, glyphs[codepoint]))
        advance = width + 1
        writer.write(width - 1, 4)
        writer.write(advance - 1, 4)
        writer.write(0, 1)  # raw bitmap
        for row in rows:
            # The resident table numbers its leftmost pixel as bit zero.
            for x in range(width):
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
    print(f"{args.output}: {len(expected)} bytes, "
          f"{len(source_codepoints())} glyphs, proportional 3-5x5")


def source_codepoints() -> tuple[int, ...]:
    return tuple(range(0x20, 0x40)) + (0x0401,) + tuple(range(0x0410, 0x0430))


if __name__ == "__main__":
    main()
