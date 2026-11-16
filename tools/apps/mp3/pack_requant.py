"""Pack libmad's Layer III requantization table exactly for an SRAM-loaded APP."""

import re
from pathlib import Path

FIRST = 512
STRIDE = 32


def pack(source: Path, output: Path) -> None:
    rows = re.findall(r"\{\s*MAD_F\((0x[0-9a-fA-F]+)\)\s*/\*.*?\*/\s*,\s*(\d+)\s*\}", source.read_text())
    values = [(int(m, 16), int(e)) for m, e in rows]
    if len(values) != 8207:
        raise ValueError("unexpected libmad requantization table")
    blocks = []
    residuals = []
    for start in range(FIRST, len(values), STRIDE):
        entries = values[start:start + STRIDE + 1]
        base, exp = entries[0]
        scaled = [m << (e - exp) for m, e in entries]
        while len(scaled) != STRIDE + 1:
            scaled.append(2 * scaled[-1] - scaled[-2])
        slope = scaled[-1] - base
        curve = scaled[16] - base - ((slope + 1) >> 1)
        if not -32768 <= curve <= 32767:
            raise ValueError("libmad curve overflow")
        blocks.append(f"  {{0x{(exp << 27) | base:08x}u, {slope}, {curve}}},")
        for j, expected in enumerate(entries[:STRIDE]):
            prediction = base + ((slope * j + 16) >> 5) + ((curve * j * (32 - j) + 128) >> 8)
            exact = scaled[j]
            error = exact - prediction
            if not -128 <= error <= 127:
                raise ValueError("libmad residual overflow")
            shift = exact >= 1 << 27
            if (exact >> shift, exp + shift) != expected:
                raise ValueError("libmad packed value differs from source")
            residuals.append(error)
    narrow_end = len(residuals) // STRIDE * STRIDE
    narrow_start = max(((at // STRIDE + 1) * STRIDE
                        for at, error in enumerate(residuals[:narrow_end])
                        if not -8 <= error <= 7), default=0)
    narrow = residuals[narrow_start:narrow_end]
    if not narrow:
        raise ValueError("no libmad residual blocks fit in four bits")
    packed = [(lo + 8) | ((hi + 8) << 4) for lo, hi in zip(narrow[::2], narrow[1::2])]
    wide = residuals[:narrow_start] + residuals[narrow_end:]
    text = ["/* Generated from libmad rq_table.dat. See its GPL license. */",
            "static const uint32_t rq_small[] = {"]
    for at in range(0, FIRST, 8):
        text.append("  " + ", ".join(f"0x{(e << 27) | m:08x}u" for m, e in values[at:at + 8]) + ",")
    text.extend(["};", "static const struct rq_block rq_blocks[] = {", *blocks, "};",
                 f"enum {{ RQ_NARROW_START = {narrow_start}, RQ_NARROW_END = {narrow_end} }};",
                 "static const int8_t rq_residuals[] = {"])
    for at in range(0, len(wide), 20):
        text.append("  " + ", ".join(map(str, wide[at:at + 20])) + ",")
    text.extend(["};", "static const uint8_t rq_nibbles[] = {"])
    for at in range(0, len(packed), 20):
        text.append("  " + ", ".join(f"0x{value:02x}" for value in packed[at:at + 20]) + ",")
    output.write_text("\n".join([*text, "};", ""]))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    pack(args.source, args.output)
