#!/usr/bin/env python3
"""Dependency-free ABI 5 APP packer used when no native host C++ exists.

The ZX0 stream writer follows the v2 format by Einar Saukas.  The greedy
parser is intentionally implemented in Python so Arduino IDE on Windows only
needs the Python installation that is already required by the APP build.
ZX0 format copyright (c) 2021 Einar Saukas, BSD-3-Clause; the complete notice
is stored in third_party/zx0/LICENSE.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path


HEADER_SIZE = 64
APP_MAX_MEMORY_SIZE = 20 * 1024
LOAD_ADDRESS = 0x20000000
MAX_OFFSET = 32640

PORTABLE_FLAG = 1
BCJ_FLAG = 2
RELOCATABLE_FLAG = 4

KINDS = {
    "focal": 1,
    "tinybasic": 2,
    "wbmp-viewer": 3,
    "app": 4,
    "chip8": 5,
    "markdown-viewer": 6,
    "setup": 7,
}


class PackError(ValueError):
    pass


class BitWriter:
    def __init__(self) -> None:
        self.output = bytearray()
        self.bit_index = 0
        self.bit_mask = 0
        # ZX0 stores the first length bit of a new-offset match in the low
        # offset byte.  At stream start the same mechanism omits the implicit
        # first literal selector.
        self.backtrack = True

    def bit(self, value: bool) -> None:
        if self.backtrack:
            if value:
                if not self.output:
                    raise PackError("invalid ZX0 backtrack")
                self.output[-1] |= 1
            self.backtrack = False
            return
        if self.bit_mask == 0:
            self.bit_mask = 0x80
            self.bit_index = len(self.output)
            self.output.append(0)
        if value:
            self.output[self.bit_index] |= self.bit_mask
        self.bit_mask >>= 1

    def byte(self, value: int) -> None:
        self.output.append(value & 0xFF)

    def gamma(self, value: int, *, inverted: bool = False) -> None:
        if value <= 0:
            raise PackError("invalid ZX0 gamma value")
        bit = 1 << (value.bit_length() - 1)
        while True:
            bit >>= 1
            if bit == 0:
                break
            self.bit(False)
            data = bool(value & bit)
            self.bit(not data if inverted else data)
        self.bit(True)


def match_length(data: bytes, position: int, candidate: int) -> int:
    limit = len(data) - position
    length = 2
    while length < limit and data[position + length] == data[candidate + length]:
        length += 1
    return length


def best_match(data: bytes, position: int, last_offset: int) -> tuple[int, int]:
    if position + 1 >= len(data):
        return 0, 0
    needle = data[position:position + 2]
    window = max(0, position - MAX_OFFSET)
    candidate = data.rfind(needle, window, position)
    best_length = 0
    best_offset = 0
    remaining = len(data) - position
    while candidate >= window:
        offset = position - candidate
        length = match_length(data, position, candidate)
        if (length > best_length or
                (length == best_length and
                 (offset == last_offset or
                  (best_offset != last_offset and offset < best_offset)))):
            best_length = length
            best_offset = offset
            if length == remaining:
                break
        candidate = data.rfind(needle, window, candidate)
    return best_length, best_offset


def greedy_tokens(data: bytes) -> list[tuple[int, int]]:
    if not data:
        raise PackError("ZX0 input is empty")
    tokens: list[tuple[int, int]] = []
    literal_start = 0
    position = 1
    last_offset = 1
    while position + 1 < len(data):
        length, offset = best_match(data, position, last_offset)
        # A two-byte match with a new offset normally costs more once the
        # surrounding literal blocks and offset selector are included.  Keep
        # it only for the compact last-offset form; otherwise leaving both
        # bytes in the current literal run produces a smaller stream.
        if length < 2 or (length == 2 and offset != last_offset):
            position += 1
            continue
        # Do not consume a short match when one literal byte exposes a
        # substantially longer one.  This small lazy step recovers most of
        # the size lost by a purely greedy parser without the quadratic RAM
        # use of the desktop optimal parser.
        if position + 2 < len(data):
            next_length, _ = best_match(data, position + 1, last_offset)
            if next_length > length + 1:
                position += 1
                continue
        tokens.append((position - literal_start, 0))
        tokens.append((length, offset))
        last_offset = offset
        literal_start = position + length
        if literal_start >= len(data):
            break
        position = literal_start + 1
    if literal_start < len(data):
        tokens.append((len(data) - literal_start, 0))
    if not tokens or tokens[0][1] != 0:
        raise PackError("invalid ZX0 token plan")
    return tokens


def zx0_encode(data: bytes) -> bytes:
    writer = BitWriter()
    position = 0
    last_offset = 1
    for length, offset in greedy_tokens(data):
        if length <= 0 or position + length > len(data):
            raise PackError("invalid ZX0 token")
        if offset == 0:
            writer.bit(False)
            writer.gamma(length)
            for value in data[position:position + length]:
                writer.byte(value)
        elif offset == last_offset:
            writer.bit(False)
            writer.gamma(length)
        else:
            writer.bit(True)
            writer.gamma((offset - 1) // 128 + 1, inverted=True)
            writer.byte((127 - ((offset - 1) % 128)) << 1)
            writer.backtrack = True
            writer.gamma(length - 1)
            last_offset = offset
        position += length
    if position != len(data):
        raise PackError("incomplete ZX0 token plan")
    writer.bit(True)
    writer.gamma(256, inverted=True)
    return bytes(writer.output)


class BitReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0
        self.bit_value = 0
        self.bit_mask = 0

    def byte(self) -> int:
        if self.position >= len(self.data):
            raise PackError("truncated ZX0 stream")
        value = self.data[self.position]
        self.position += 1
        return value

    def bit(self) -> int:
        self.bit_mask >>= 1
        if self.bit_mask == 0:
            self.bit_mask = 0x80
            self.bit_value = self.byte()
        return int(bool(self.bit_value & self.bit_mask))

    def gamma(self, *, inverted: bool, first: int | None = None) -> int:
        result = 1
        current = self.bit() if first is None else first
        while current == 0:
            result = (result << 1) | (self.bit() ^ int(inverted))
            current = self.bit()
        return result


def zx0_decode(data: bytes, expected_size: int) -> bytes:
    reader = BitReader(data)
    output = bytearray()
    last_offset = 1
    state = "literal"
    while True:
        if state == "literal":
            length = reader.gamma(inverted=False)
            for _ in range(length):
                output.append(reader.byte())
            selector = reader.bit()
            if selector:
                state = "new"
            else:
                length = reader.gamma(inverted=False)
                if last_offset > len(output):
                    raise PackError("invalid ZX0 last offset")
                for _ in range(length):
                    output.append(output[-last_offset])
                state = "new" if reader.bit() else "literal"
        else:
            high = reader.gamma(inverted=True)
            if high == 256:
                if len(output) != expected_size or reader.position != len(data):
                    raise PackError("invalid ZX0 end marker")
                return bytes(output)
            if high > 255:
                raise PackError("invalid ZX0 offset")
            low = reader.byte()
            last_offset = high * 128 - (low >> 1)
            length = reader.gamma(inverted=False, first=low & 1) + 1
            if last_offset <= 0 or last_offset > len(output):
                raise PackError("invalid ZX0 offset")
            for _ in range(length):
                output.append(output[-last_offset])
            state = "new" if reader.bit() else "literal"
        if len(output) > expected_size:
            raise PackError("ZX0 output exceeds image")


def bcj_transform(data: bytes, encode: bool) -> bytes:
    output = bytearray(data)
    index = 0
    while index + 3 < len(output):
        if ((output[index + 1] & 0xF8) == 0xF0 and
                (output[index + 3] & 0xF8) == 0xF8):
            address = (((output[index + 1] & 7) << 19) |
                       (output[index] << 11) |
                       ((output[index + 3] & 7) << 8) |
                       output[index + 2]) << 1
            address = address + index + 4 if encode else address - index - 4
            address = (address & 0xFFFFFFFF) >> 1
            output[index + 1] = 0xF0 | ((address >> 19) & 7)
            output[index] = (address >> 11) & 0xFF
            output[index + 3] = 0xF8 | ((address >> 8) & 7)
            output[index + 2] = address & 0xFF
            index += 4
        else:
            index += 2
    return bytes(output)


def validate_relocations(table: bytes, image: bytes, memory_size: int) -> int:
    position = 0
    end = 0
    count = 0
    while position < len(table):
        gap = 0
        shift = 0
        while True:
            if position >= len(table) or shift > 14:
                raise PackError("malformed relocation table")
            value = table[position]
            position += 1
            if shift and value == 0:
                raise PackError("non-canonical relocation table")
            gap |= (value & 0x7F) << shift
            if not value & 0x80:
                break
            shift += 7
        offset = end + gap
        if offset + 4 > len(image):
            raise PackError("relocation is outside the image")
        pointer = struct.unpack_from("<I", image, offset)[0]
        if not LOAD_ADDRESS <= pointer <= LOAD_ADDRESS + memory_size:
            raise PackError("relocation does not refer to the APP image")
        end = offset + 4
        count += 1
    return count


def type_magic(value: str | None) -> int:
    if value is None:
        return 0
    if len(value) != 2 or not value.isascii() or not value.isalnum():
        raise PackError("handled magic must contain two ASCII letters or digits")
    return ord(value[0]) | (ord(value[1]) << 8)


def pack(args: argparse.Namespace) -> bytes:
    image = args.image.read_bytes()
    table = args.relocations.read_bytes()
    memory_size = args.memory_size
    if not image or len(image) > memory_size or memory_size > APP_MAX_MEMORY_SIZE:
        raise PackError("module exceeds the 20 KiB APP image limit")
    if args.entry_offset < 0 or args.entry_offset >= len(image) or args.entry_offset & 1:
        raise PackError("entry offset must be aligned and inside the image")
    if args.load_address != LOAD_ADDRESS:
        raise PackError("current APP ABI has a fixed virtual link base")
    relocation_count = validate_relocations(table, image, memory_size)

    plain = zx0_encode(image)
    if zx0_decode(plain, len(image)) != image:
        raise PackError("internal plain ZX0 verification failed")
    filtered = bcj_transform(image, True)
    if bcj_transform(filtered, False) != image:
        raise PackError("BCJ round-trip failed")
    bcj = zx0_encode(filtered)
    if zx0_decode(bcj, len(filtered)) != filtered:
        raise PackError("internal BCJ ZX0 verification failed")
    use_bcj = len(bcj) < len(plain)
    code = bcj if use_bcj else plain
    print(f"ZX0 candidates: plain={len(plain)} BCJ={len(bcj)}; "
          f"selected={'BCJ' if use_bcj else 'plain'}")

    stored = code + table
    if HEADER_SIZE + len(stored) > HEADER_SIZE + APP_MAX_MEMORY_SIZE:
        raise PackError("module exceeds the 20 KiB APP container limit")
    flags = PORTABLE_FLAG | RELOCATABLE_FLAG | (BCJ_FLAG if use_bcj else 0)
    header = bytearray(HEADER_SIZE)
    header[:8] = b"MK61APP\0"
    struct.pack_into("<HHHBBIIIIIIIIIIH", header, 8,
                     1, HEADER_SIZE, 5, KINDS[args.kind], 1, flags,
                     args.load_address, len(stored), len(image), memory_size,
                     args.entry_offset, len(code), relocation_count,
                     zlib.crc32(stored), zlib.crc32(image),
                     type_magic(args.handled_magic))
    struct.pack_into("<H", header, 58, 0)
    struct.pack_into("<I", header, 60, zlib.crc32(header[:60]))
    return bytes(header) + stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--relocations", type=Path, required=True)
    parser.add_argument("--memory-size", type=lambda x: int(x, 0), required=True)
    parser.add_argument("--entry-offset", type=lambda x: int(x, 0), required=True)
    parser.add_argument("--load-address", type=lambda x: int(x, 0),
                        default=LOAD_ADDRESS)
    parser.add_argument("--handled-magic")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        module = pack(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(module)
        ratio = (len(module) - HEADER_SIZE) * 100.0 / args.image.stat().st_size
        print(f"{args.output}: {len(module)} bytes, payload ratio {ratio:.1f}%")
    except (OSError, PackError, KeyError, struct.error) as error:
        parser.exit(2, f"mk61_module_pack: {error}\n")


if __name__ == "__main__":
    main()
