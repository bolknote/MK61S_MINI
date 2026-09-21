#!/usr/bin/env python3
"""Convert a Unicode-range FMK1 font into the byte-indexed M8 FMK2 format."""

from __future__ import annotations

import argparse
from pathlib import Path

from m8_codec import encode as encode_m8


HEADER_SIZE = 16


class BitReader:
    def __init__(self, data: bytes, position: int) -> None:
        self.data = data
        self.position = position

    def read(self, count: int) -> int:
        if self.position + count > len(self.data) * 8:
            raise ValueError("truncated FMK1 bitstream")
        value = 0
        for _ in range(count):
            value = (value << 1) | (
                (self.data[self.position // 8] >>
                 (7 - self.position % 8)) & 1
            )
            self.position += 1
        return value

    def skip_record(self, pixels: int) -> None:
        mode = self.read(1)
        produced = 0
        while produced < pixels:
            if mode == 0:
                self.read(1)
                produced += 1
                continue
            kind = self.read(1)
            if kind == 0:
                count = self.read(4) + 1
                self.read(count)
            else:
                count = self.read(5) + 2
                self.read(1)
            if produced + count > pixels:
                raise ValueError("invalid FMK1 bitmap run")
            produced += count


class BitWriter:
    def __init__(self, prefix: bytes) -> None:
        self.data = bytearray(prefix)
        self.position = len(prefix) * 8

    def bit(self, value: int) -> None:
        byte = self.position // 8
        if byte == len(self.data):
            self.data.append(0)
        if value:
            self.data[byte] |= 0x80 >> (self.position & 7)
        self.position += 1

    def copy(self, source: bytes, begin: int, end: int) -> None:
        for position in range(begin, end):
            self.bit((source[position // 8] >> (7 - position % 8)) & 1)


def le16(data: bytes, offset: int) -> int:
    return data[offset] | data[offset + 1] << 8


def put_le16(data: bytearray, offset: int, value: int) -> None:
    data[offset] = value & 0xFF
    data[offset + 1] = value >> 8


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for index, byte in enumerate(data):
        if index in (14, 15):
            byte = 0
        crc ^= byte << 8
        for _ in range(8):
            crc = (((crc << 1) ^ 0x1021) if crc & 0x8000
                   else crc << 1) & 0xFFFF
    return crc


def m8_ranges(values: list[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start = previous = values[0]
    count = 1
    for value in values[1:]:
        if value == previous + 1:
            count += 1
        else:
            result.append((start, count))
            start, count = value, 1
        previous = value
    result.append((start, count))
    return result


def convert(source: bytes) -> bytes:
    if len(source) < HEADER_SIZE or source[:4] != b"FMK1":
        raise ValueError("input is not FMK1")
    if le16(source, 12) != len(source) or le16(source, 14) != crc16(source):
        raise ValueError("FMK1 size or CRC is invalid")
    glyph_count = le16(source, 8)
    range_count = source[10]
    ranges_end = HEADER_SIZE + range_count * 3
    if not glyph_count or not range_count or ranges_end > len(source):
        raise ValueError("invalid FMK1 ranges")

    codepoints: list[int] = []
    for index in range(range_count):
        offset = HEADER_SIZE + index * 3
        first = le16(source, offset)
        count = source[offset + 2] + 1
        codepoints.extend(range(first, first + count))
    if len(codepoints) != glyph_count:
        raise ValueError("FMK1 glyph count does not match its ranges")

    monospaced = bool(source[4] & 1)
    height = source[6]
    default_width = source[5]
    reader = BitReader(source, ranges_end * 8)
    records: list[tuple[int, int]] = []
    for _ in range(glyph_count):
        begin = reader.position
        width = default_width
        if not monospaced:
            width = reader.read(4) + 1
            reader.read(4)
        reader.skip_record(width * height)
        records.append((begin, reader.position))
    if len(source) * 8 - reader.position >= 8:
        raise ValueError("FMK1 contains trailing data")

    glyphs: list[tuple[int, int, int]] = []
    for codepoint, (begin, end) in zip(codepoints, records, strict=True):
        try:
            encoded = encode_m8(chr(codepoint))
        except UnicodeEncodeError as error:
            raise ValueError(
                f"FMK1 glyph U+{codepoint:04X} is not representable in M8"
            ) from error
        if len(encoded) != 1:
            raise ValueError(f"FMK1 glyph U+{codepoint:04X} is not one M8 byte")
        glyphs.append((encoded[0], begin, end))
    glyphs.sort()
    values = [glyph[0] for glyph in glyphs]
    if len(values) != len(set(values)):
        raise ValueError("multiple FMK1 glyphs map to one M8 byte")
    ranges = m8_ranges(values)

    prefix = bytearray(source[:HEADER_SIZE])
    prefix[:4] = b"FMK2"
    prefix[10] = len(ranges)
    prefix[11] = 0
    put_le16(prefix, 12, 0)
    put_le16(prefix, 14, 0)
    for first, count in ranges:
        prefix += bytes((first, count - 1))
    writer = BitWriter(prefix)
    for _, begin, end in glyphs:
        writer.copy(source, begin, end)
    if len(writer.data) > 0xFFFF:
        raise ValueError("FMK2 output is too large")
    put_le16(writer.data, 12, len(writer.data))
    put_le16(writer.data, 14, crc16(writer.data))
    return bytes(writer.data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = convert(args.input.read_bytes())
        if args.check:
            if not args.output.is_file() or args.output.read_bytes() != result:
                raise ValueError(f"{args.output}: generated FMK2 differs")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(result)
    except (OSError, ValueError) as error:
        parser.exit(1, f"FMK conversion: {error}\n")
    print(f"{args.output}: {len(result)} bytes, FMK2/M8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
