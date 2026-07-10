#!/usr/bin/env python3
"""Compare RLE parsing strategies and optional LZO1X on binary files.

The two base formats are described at:
https://bolknote.ru/all/kakoy-rle-luchshe/

"bolk" stores a repeated byte twice followed by an extra-repeat count.
"packbits" uses one control byte to select a literal block or a run.
The optimal PackBits parser uses dynamic programming, so it considers every
legal sequence of literal and run blocks instead of committing greedily.
Pass --lzo to add LZO1X-1 and its lower-memory 1-11 compressor through the
system liblzo2. Every encoded stream is decoded and checked before reporting.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Encoded:
    name: str
    data: bytes


class Lzo1x:
    """Small ctypes adapter for the system liblzo2 benchmark dependency."""

    def __init__(self, library: str | None = None) -> None:
        library = library or ctypes.util.find_library("lzo2")
        if library is None:
            raise RuntimeError("liblzo2 was not found")
        self.library_name = library
        self.lib = ctypes.CDLL(library)
        self.decompress = self.lib.lzo1x_decompress_safe
        self.decompress.argtypes = (
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
        )
        self.decompress.restype = ctypes.c_int

    def compress(self, data: bytes, symbol: str, work_slots: int) -> bytes:
        function = getattr(self.lib, symbol)
        function.argtypes = (
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
        )
        function.restype = ctypes.c_int

        source = ctypes.create_string_buffer(data)
        output_capacity = len(data) + len(data) // 16 + 64 + 3
        output = ctypes.create_string_buffer(output_capacity)
        output_len = ctypes.c_size_t(output_capacity)
        # lzo_sizeof_dict_t is pointer-sized. On a 32-bit target these slot
        # counts correspond to 64 KiB for LZO1X-1 and 8 KiB for 1-11.
        work = ctypes.create_string_buffer(work_slots * ctypes.sizeof(ctypes.c_void_p))
        status = function(source, len(data), output, ctypes.byref(output_len), work)
        if status != 0:
            raise RuntimeError(f"{symbol} failed with LZO status {status}")
        encoded = output.raw[: output_len.value]
        self._check_round_trip(data, encoded)
        return encoded

    def _check_round_trip(self, expected: bytes, encoded: bytes) -> None:
        output = ctypes.create_string_buffer(len(expected))
        output_len = ctypes.c_size_t(len(expected))
        status = self.decompress(
            encoded,
            len(encoded),
            output,
            ctypes.byref(output_len),
            None,
        )
        if status != 0 or output_len.value != len(expected):
            raise RuntimeError(f"LZO round-trip failed with status {status}")
        if output.raw[: output_len.value] != expected:
            raise RuntimeError("LZO round-trip produced different bytes")


def runs(data: bytes) -> Iterable[tuple[int, int]]:
    """Yield (byte, run length) pairs."""
    start = 0
    while start < len(data):
        end = start + 1
        while end < len(data) and data[end] == data[start]:
            end += 1
        yield data[start], end - start
        start = end


def bolk_encode(data: bytes) -> bytes:
    """Encode byte, byte, extra-count runs with an 8-bit count."""
    out = bytearray()
    for value, length in runs(data):
        while length:
            if length == 1:
                out.append(value)
                break
            chunk = min(length, 257)
            out.extend((value, value, chunk - 2))
            length -= chunk
    return bytes(out)


def bolk_decode(data: bytes) -> bytes:
    out = bytearray()
    pos = 0
    while pos < len(data):
        value = data[pos]
        pos += 1
        out.append(value)
        if pos < len(data) and data[pos] == value:
            if pos + 1 >= len(data):
                raise ValueError("truncated Bolk run")
            pos += 1
            extra = data[pos]
            pos += 1
            out.extend((value,) * (extra + 1))
    return bytes(out)


def packbits_emit_literal(out: bytearray, block: bytes, literal_limit: int) -> None:
    if not 1 <= len(block) <= literal_limit:
        raise ValueError("invalid literal block length")
    out.append(len(block) - 1)
    out.extend(block)


def packbits_emit_run(
    out: bytearray, value: int, length: int, literal_limit: int
) -> None:
    run_limit = 256 - literal_limit
    if not 1 <= length <= run_limit:
        raise ValueError("invalid run length")
    out.extend((literal_limit + length - 1, value))


def packbits_greedy_encode(
    data: bytes,
    *,
    run_threshold: int,
    literal_limit: int = 128,
) -> bytes:
    """Greedily encode maximal runs at or above run_threshold."""
    if not 2 <= run_threshold <= 256 - literal_limit:
        raise ValueError("run threshold is outside the encodable range")

    run_limit = 256 - literal_limit
    out = bytearray()
    literals = bytearray()

    def flush_literals() -> None:
        while literals:
            size = min(len(literals), literal_limit)
            packbits_emit_literal(out, bytes(literals[:size]), literal_limit)
            del literals[:size]

    for value, length in runs(data):
        if length < run_threshold:
            literals.extend((value,) * length)
            continue

        flush_literals()
        while length >= run_threshold:
            size = min(length, run_limit)
            packbits_emit_run(out, value, size, literal_limit)
            length -= size
        literals.extend((value,) * length)

    flush_literals()
    return bytes(out)


def _run_lengths(data: bytes) -> list[int]:
    lengths = [0] * len(data)
    for pos in range(len(data) - 1, -1, -1):
        lengths[pos] = 1
        if pos + 1 < len(data) and data[pos] == data[pos + 1]:
            lengths[pos] += lengths[pos + 1]
    return lengths


def packbits_optimal_encode(
    data: bytes,
    *,
    literal_limit: int = 128,
    long_runs: bool = False,
) -> bytes:
    """Find the smallest encoding over all literal/run block choices.

    With long_runs enabled, 0xff is reserved as an escape followed by a
    little-endian 16-bit run length and the repeated byte.
    """
    if not 1 <= literal_limit <= 255:
        raise ValueError("literal_limit must be in 1..255")

    short_run_limit = 256 - literal_limit - (1 if long_runs else 0)
    if short_run_limit < 1:
        raise ValueError("no control values remain for short runs")

    size = len(data)
    same = _run_lengths(data)
    costs = [size * 2 + 1] * (size + 1)
    costs[size] = 0
    choices: list[tuple[str, int] | None] = [None] * size

    for pos in range(size - 1, -1, -1):
        max_literal = min(literal_limit, size - pos)
        for length in range(1, max_literal + 1):
            cost = 1 + length + costs[pos + length]
            if cost < costs[pos]:
                costs[pos] = cost
                choices[pos] = ("literal", length)

        max_short_run = min(short_run_limit, same[pos])
        for length in range(2, max_short_run + 1):
            cost = 2 + costs[pos + length]
            if cost < costs[pos]:
                costs[pos] = cost
                choices[pos] = ("run", length)

        if long_runs:
            max_long_run = min(65535, same[pos])
            for length in range(short_run_limit + 1, max_long_run + 1):
                cost = 4 + costs[pos + length]
                if cost < costs[pos]:
                    costs[pos] = cost
                    choices[pos] = ("long-run", length)

    out = bytearray()
    pos = 0
    while pos < size:
        choice = choices[pos]
        if choice is None:
            raise AssertionError(f"no encoding choice at offset {pos}")
        kind, length = choice
        if kind == "literal":
            packbits_emit_literal(out, data[pos : pos + length], literal_limit)
        elif kind == "run":
            packbits_emit_run(out, data[pos], length, literal_limit)
        else:
            out.append(0xFF)
            out.extend(length.to_bytes(2, "little"))
            out.append(data[pos])
        pos += length

    if len(out) != costs[0]:
        raise AssertionError("dynamic-programming cost does not match output")
    return bytes(out)


def packbits_decode(
    data: bytes,
    *,
    literal_limit: int = 128,
    long_runs: bool = False,
) -> bytes:
    short_run_limit = 256 - literal_limit - (1 if long_runs else 0)
    out = bytearray()
    pos = 0
    while pos < len(data):
        control = data[pos]
        pos += 1
        if long_runs and control == 0xFF:
            if pos + 3 > len(data):
                raise ValueError("truncated long run")
            length = int.from_bytes(data[pos : pos + 2], "little")
            value = data[pos + 2]
            pos += 3
            out.extend((value,) * length)
        elif control < literal_limit:
            length = control + 1
            if pos + length > len(data):
                raise ValueError("truncated literal block")
            out.extend(data[pos : pos + length])
            pos += length
        else:
            length = control - literal_limit + 1
            if not 1 <= length <= short_run_limit or pos >= len(data):
                raise ValueError("invalid short run")
            out.extend((data[pos],) * length)
            pos += 1
    return bytes(out)


def benchmark(
    data: bytes,
    scan_splits: bool,
    lzo: Lzo1x | None = None,
) -> list[Encoded]:
    results = [
        Encoded("Bolk", bolk_encode(data)),
        Encoded(
            "PackBits greedy >=2",
            packbits_greedy_encode(data, run_threshold=2),
        ),
        Encoded(
            "PackBits greedy >=3",
            packbits_greedy_encode(data, run_threshold=3),
        ),
        Encoded("PackBits optimal", packbits_optimal_encode(data)),
        Encoded(
            "PackBits optimal + u16 runs",
            packbits_optimal_encode(data, long_runs=True),
        ),
    ]

    if scan_splits:
        best_limit = min(
            range(1, 255),
            key=lambda limit: len(
                packbits_optimal_encode(data, literal_limit=limit)
            ),
        )
        results.append(
            Encoded(
                f"PackBits optimal split {best_limit}/{256 - best_limit}",
                packbits_optimal_encode(data, literal_limit=best_limit),
            )
        )

    if lzo is not None:
        results.extend(
            (
                Encoded(
                    "LZO1X-1 (64 KiB work RAM on 32-bit)",
                    lzo.compress(data, "lzo1x_1_compress", 16384),
                ),
                Encoded(
                    "LZO1X-1-11 (8 KiB work RAM on 32-bit)",
                    lzo.compress(data, "lzo1x_1_11_compress", 2048),
                ),
            )
        )

    for result in results:
        if result.name.startswith("LZO"):
            continue
        if result.name == "Bolk":
            decoded = bolk_decode(result.data)
        else:
            long_runs = result.name.endswith("u16 runs")
            if result.name.startswith("PackBits optimal split"):
                literal_limit = int(
                    result.name.rsplit(" ", 1)[1].split("/", 1)[0]
                )
            else:
                literal_limit = 128
            decoded = packbits_decode(
                result.data,
                literal_limit=literal_limit,
                long_runs=long_runs,
            )
        if decoded != data:
            raise AssertionError(f"{result.name} failed to round-trip")

    return results


def print_results(
    name: str,
    data: bytes,
    scan_splits: bool,
    lzo: Lzo1x | None,
) -> None:
    print(f"\n{name}: {len(data)} bytes")
    for result in benchmark(data, scan_splits, lzo):
        delta = len(result.data) - len(data)
        ratio = 100.0 * len(result.data) / len(data) if data else 0.0
        print(
            f"  {result.name:<38} {len(result.data):>5} bytes  "
            f"({ratio:6.2f}%, {delta:+d})"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--combine",
        action="store_true",
        help="also benchmark all input files concatenated in argument order",
    )
    parser.add_argument(
        "--scan-splits",
        action="store_true",
        help="try every one-byte control split between literals and runs",
    )
    parser.add_argument(
        "--lzo",
        action="store_true",
        help="also benchmark LZO1X-1 and LZO1X-1-11 through liblzo2",
    )
    parser.add_argument(
        "--lzo-library",
        help="path or loader name for liblzo2 (implies --lzo)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        lzo = Lzo1x(args.lzo_library) if args.lzo or args.lzo_library else None
    except (AttributeError, OSError, RuntimeError) as error:
        raise SystemExit(f"LZO unavailable: {error}") from error
    if lzo is not None:
        print(f"LZO library: {lzo.library_name}")
    inputs = [(path.name, path.read_bytes()) for path in args.files]
    for name, data in inputs:
        print_results(name, data, args.scan_splits, lzo)
    if args.combine and len(inputs) > 1:
        print_results(
            " + ".join(name for name, _ in inputs),
            b"".join(data for _, data in inputs),
            args.scan_splits,
            lzo,
        )


if __name__ == "__main__":
    main()
