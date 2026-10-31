#!/usr/bin/env python3
"""Decode one bounded ASCII result emitted after an APP has restored its state."""
import re
import zlib

ROWS = {'lookup': 6, 'pop': 12, 'sqrt': 12, 'rsqrt': 12}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def parse(raw, variant, rounds=7):
    require(isinstance(raw, bytes) and len(raw) <= 32768 and b'\0' not in raw,
            'Invalid or oversized result exchange')
    require(variant in ROWS and 1 <= rounds <= 7, 'Unsupported result shape')
    expected = 256 + ROWS[variant] * (48 + 40 * rounds)
    lines = raw.split(b'\r\n')
    reserved = [i for i, line in enumerate(lines) if b'IFO4:' in line]
    require(reserved and reserved == list(range(reserved[0], reserved[-1] + 1)),
            'Missing, split, or interleaved result frame')
    frame = lines[reserved[0]:reserved[-1] + 1]
    begin = re.fullmatch(rb'IFO4:B:([0-9A-F]{8}):([0-9A-F]{8})', frame[0])
    end = re.fullmatch(rb'IFO4:E:([0-9A-F]{8}):([0-9A-F]{8})', frame[-1])
    require(begin is not None and end is not None and begin.groups() == end.groups(),
            'Missing, duplicate, or mismatched result bookends')
    length, checksum = (int(v, 16) for v in begin.groups())
    require(length == expected, 'Wrong schema4 result length')
    result = bytearray()
    for line in frame[1:-1]:
        data = re.fullmatch(rb'IFO4:D:([0-9A-F]{8}):([0-9A-F]{2,64})', line)
        require(data is not None and len(data[2]) % 2 == 0, 'Malformed result data line')
        offset = int(data[1], 16)
        chunk = bytes.fromhex(data[2].decode('ascii'))
        require(offset == len(result) and len(chunk) == min(32, length - offset),
                'Noncontiguous, duplicate, short, or oversized result chunk')
        result.extend(chunk)
    require(len(result) == length and zlib.crc32(result) == checksum,
            'Truncated or corrupted result payload')
    return bytes(result)
