#!/usr/bin/env python3
"""Pack reviewed native monochrome atlases; no font engine is needed to build FW."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATLAS_DIR = ROOT / "tools/.fmk-font/ui-atlases"
NAMES = ("pixel-12", "pixel-14", "pixel-16")
EXPECTED_HEIGHTS = {"pixel-12": 12, "pixel-14": 14, "pixel-16": 17}
SOURCE_HASHES = {
    "pixel-12": "3fee5d1cf9d5af61aee234beccaf3e6e0229388717efa1e27c62c0097641912f",
    "pixel-14": "dd2388475c04d1bba6a03b2b6a7684bae39a36d6cbb41b4d4f7f560a8cbf2f78",
    "pixel-16": "2f4720dd48f2ce5f6c4c790f5562efc9a1f084e5b52412fab74024f4712b4bda",
}
SUPPLEMENT_HASH = "b9a7765b998fc8d486252ce01b3fb6e880df934612599beb66bed888133a6b11"
SUPPLEMENT_CODEPOINTS = {0x02B8, 0x02E3, 0x221A, 0x2260, 0x2264, 0x2265, 0x22BB}
SOURCE_MISSING = SUPPLEMENT_CODEPOINTS
LINE_GAPS = {12: 1, 14: 2, 17: 2}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_atlases(directory=ATLAS_DIR):
    supplement_raw = (directory / "m8-supplement.json").read_bytes()
    require(hashlib.sha256(supplement_raw).hexdigest() == SUPPLEMENT_HASH,
            "M8 supplement: reviewed source SHA-256 changed")
    supplement = json.loads(supplement_raw)
    require(supplement["schema"] == 1 and set(supplement["faces"]) == set(NAMES),
            "M8 supplement: unexpected schema or faces")
    result = []
    for name in NAMES:
        raw = (directory / f"{name}.json").read_bytes()
        require(hashlib.sha256(raw).hexdigest() == SOURCE_HASHES[name],
                f"{name}: reviewed source SHA-256 changed")
        atlas = json.loads(raw)
        require(atlas["schema"] == 1 and
                atlas["height"] == EXPECTED_HEIGHTS[name],
                f"{name}: unexpected metrics")
        require(atlas["height"] == atlas["ascent"] + atlas["descent"],
                f"{name}: inconsistent line box")
        glyphs = {glyph["codepoint"]: glyph for glyph in atlas["glyphs"]}
        require(len(glyphs) == len(atlas["glyphs"]), f"{name}: duplicate glyph")
        require(set(atlas["missing"]) == SOURCE_MISSING,
                f"{name}: unexpected missing source characters")
        additions = supplement["faces"][name]
        require({glyph["codepoint"] for glyph in additions} == SUPPLEMENT_CODEPOINTS and
                len(additions) == len(SUPPLEMENT_CODEPOINTS),
                f"{name}: incomplete M8 supplement")
        for addition in additions:
            cp, rows = addition["codepoint"], addition["rows"]
            require(cp not in glyphs and rows and len(set(map(len, rows))) == 1,
                    f"{name}/{cp}: invalid supplemental raster")
            width = len(rows[0])
            advance = width + 1
            glyphs[cp] = {
                "codepoint": cp, "width": width, "height": len(rows),
                "bearing_x": 0, "bearing_y": addition["bearing_y"],
                "safe_bearing_x": 0, "native_advance": advance,
                "advance": advance, "rows": rows,
            }
        atlas["missing"] = sorted(set(atlas["missing"]) - SUPPLEMENT_CODEPOINTS)
        for cp, glyph in glyphs.items():
            w, h = glyph["width"], glyph["height"]
            x, y = glyph["safe_bearing_x"], glyph["bearing_y"]
            require(1 <= w <= 16 and 1 <= h <= atlas["height"],
                    f"{name}/{cp}: unsupported dimensions")
            require(0 <= x <= 16 and x + w < glyph["advance"] <= 32,
                    f"{name}/{cp}: no safe inter-glyph gap")
            require(0 <= atlas["ascent"] - y and h - y <= atlas["descent"],
                    f"{name}/{cp}: outside baseline envelope")
            require(len(glyph["rows"]) == h and all(
                len(row) == w and set(row) <= {"0", "1"} for row in glyph["rows"]),
                f"{name}/{cp}: malformed raster")
        atlas["by_codepoint"] = glyphs
        result.append(atlas)
    repertoire = sorted(set(result[0]["by_codepoint"]) | set(result[0]["missing"]))
    require(len(repertoire) == 181 and repertoire[:95] == list(range(32, 127)),
            "unexpected repertoire")
    for name, atlas in zip(NAMES, result):
        actual = set(atlas["by_codepoint"])
        require(actual <= set(repertoire) and
                set(repertoire) - actual == set(atlas["missing"]),
                f"{name}: inconsistent missing characters")
        require(not atlas["missing"], f"{name}: incomplete M8 repertoire")
    return result, repertoire


def pack_glyph(glyph):
    bits = "".join(glyph["rows"])
    bits += "0" * (-len(bits) % 8)
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


def record_values(offset, glyph):
    values = (offset, glyph["width"], glyph["height"],
              glyph["safe_bearing_x"], glyph["bearing_y"], glyph["advance"])
    bounds = ((0, 0xFFE), (1, 15), (1, 15), (0, 7), (-16, 15), (1, 31))
    require(all(low <= value <= high for value, (low, high) in zip(values, bounds)),
            f"compact UI glyph metadata overflow: {values}")
    return values


def pool_bitmaps(values):
    # Byte overlap changes storage only. Each glyph still exposes the original
    # tight MSB raster, with no unpacking or temporary render buffer.
    parts = []
    for value in sorted(set(values), key=lambda v: (-len(v), v)):
        if not any(value in part for part in parts):
            parts.append(value)
    while len(parts) > 1:
        best = (0, 0, 1)
        for left, a in enumerate(parts):
            for right, b in enumerate(parts):
                if left == right:
                    continue
                for size in range(min(len(a), len(b)), best[0], -1):
                    if a[-size:] == b[:size]:
                        best = (size, left, right)
                        break
        size, left, right = best
        if not size:
            break
        merged = parts[left] + parts[right][size:]
        parts = [part for index, part in enumerate(parts)
                 if index not in (left, right) and part not in merged] + [merged]
    result = b"".join(parts)
    require(all(value in result for value in values), "bitmap pooling lost a glyph")
    return result


def generate(directory=ATLAS_DIR):
    atlases, repertoire = load_atlases(directory)
    ascii_count = 0x7F - 0x20
    non_ascii = repertoire[ascii_count:]
    lines = ["// Generated by tools/generate_ui_fonts.py; do not edit.",
             "// Source/permissions: tools/.fmk-font/ui-atlases/README.md.",
             "// Row-major MSB-first bits, tightly packed within each glyph.",
             f"static constexpr unsigned GLYPH_COUNT = {len(repertoire)};",
             f"static constexpr unsigned ASCII_GLYPH_COUNT = {ascii_count};",
             f"static constexpr unsigned NON_ASCII_GLYPH_COUNT = {len(non_ascii)};",
             "static const uint16_t NON_ASCII_CODEPOINTS[NON_ASCII_GLYPH_COUNT] = {"]
    for start in range(0, len(non_ascii), 12):
        lines.append("  " + ", ".join(f"0x{cp:04X}" for cp in non_ascii[start:start + 12]) + ",")
    lines.append("};")
    bitmap = pool_bitmaps([pack_glyph(atlas["by_codepoint"][cp])
                           for atlas in atlases for cp in repertoire])
    lines.append("static const uint8_t PIXEL_BITMAP[] = {")
    for start in range(0, len(bitmap), 16):
        lines.append("  " + ", ".join(f"0x{v:02X}" for v in bitmap[start:start + 16]) + ",")
    lines.append("};")
    bitmap_bytes = len(bitmap)
    for name, atlas in zip(NAMES, atlases):
        symbol = name.upper().replace("-", "_")
        metrics = []
        entries = []
        for cp in repertoire:
            glyph = atlas["by_codepoint"].get(cp)
            require(glyph is not None, "reviewed repertoire must be complete")
            packed = pack_glyph(glyph)
            offset = bitmap.find(packed)
            require(offset >= 0, "shared bitmap misses a glyph")
            values = record_values(offset, glyph)
            shape = values[1:]
            if shape not in metrics:
                metrics.append(shape)
            require(len(metrics) <= 64, "UI metric dictionary exceeds six bits")
            entries.append(values[0] | (metrics.index(shape) << 12))
        # Twenty-one metric bits; three guards permit every four-byte read.
        packed_metrics = bytearray((len(metrics) * 21 + 7) // 8 + 3)
        for index, (width, height, x, y, advance) in enumerate(metrics):
            value = width | (height << 4) | (x << 8) | ((y & 31) << 11) | (advance << 16)
            bit = index * 21
            encoded = value << (bit & 7)
            for byte in range(4):
                packed_metrics[bit // 8 + byte] |= (encoded >> (byte * 8)) & 255
        lines.append(f"static const uint8_t {symbol}_METRICS[] = {{")
        for start in range(0, len(packed_metrics), 16):
            lines.append("  " + ", ".join(f"0x{v:02X}" for v in packed_metrics[start:start + 16]) + ",")
        lines.append("};")
        # Twelve offset bits and six metric-index bits; two zero guard bytes
        # make the renderer's final three-byte read valid at every bit position.
        packed_records = bytearray((len(entries) * 18 + 7) // 8 + 2)
        for index, value in enumerate(entries):
            bit = index * 18
            encoded = value << (bit & 7)
            for byte in range(3):
                packed_records[bit // 8 + byte] |= (encoded >> (byte * 8)) & 255
        lines.append(f"static const uint8_t {symbol}_RECORDS[] = {{")
        for start in range(0, len(packed_records), 16):
            lines.append("  " + ", ".join(f"0x{v:02X}" for v in packed_records[start:start+16]) + ",")
        lines.append("};")
    lines.append("static const FaceData FACES[] = {")
    for name, atlas in zip(NAMES, atlases):
        symbol = name.upper().replace("-", "_")
        lines.append("  {%s_RECORDS, %s_METRICS, {%d, %d, %d, %d, %d}}," % (
            symbol, symbol, atlas["height"], atlas["ascent"], atlas["descent"],
            LINE_GAPS[atlas["height"]], atlas["ppem"]))
    lines.extend(("};", f"// Packed bitmap bytes (all {len(NAMES)} faces): {bitmap_bytes}.", ""))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "code/ui_font_data.inc")
    parser.add_argument("--check", action="store_true", help="fail if generated file differs")
    args = parser.parse_args()
    expected = generate()
    if args.check:
        require(args.output.read_text() == expected, "generated UI font data is stale")
        print(f"UI font data matches all {len(NAMES)} reviewed atlases")
    else:
        args.output.write_text(expected)
        print(f"Generated {args.output}")


if __name__ == "__main__":
    main()
