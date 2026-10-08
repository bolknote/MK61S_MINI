#!/usr/bin/env python3
"""Compare production C++ pixels and metrics against every reviewed atlas."""

import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("generator", ROOT / "tools/generate_ui_fonts.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def check_record_bounds():
    glyph = dict(width=15, height=15, safe_bearing_x=7, bearing_y=-16, advance=31)
    assert generator.record_values(0x7FE, glyph) == (0x7FE, 15, 15, 7, -16, 31)
    for offset, changes in ((-1, {}), (0x7FF, {}), (0xFFFF, {}),
                            (0, {"width": 0}), (0, {"width": 16}),
                            (0, {"height": 0}), (0, {"height": 16}),
                            (0, {"safe_bearing_x": -1}), (0, {"safe_bearing_x": 8}),
                            (0, {"bearing_y": -17}), (0, {"bearing_y": 16}),
                            (0, {"advance": 0}), (0, {"advance": 32})):
        try:
            generator.record_values(offset, glyph | changes)
        except ValueError:
            pass
        else:
            raise AssertionError(f"truncated glyph metadata accepted: {offset}, {changes}")


def main():
    check_record_bounds()
    atlases, repertoire = generator.load_atlases()
    actual = subprocess.check_output([sys.argv[1], "--dump"], text=True).splitlines()
    assert len(actual) == len(repertoire) * len(atlases)
    compared_pixels = 0
    for line, (face, cp) in zip(
            actual, ((i, cp) for i in range(len(atlases)) for cp in repertoire),
            strict=True):
        fields = line.split()
        assert len(fields) == 9
        values = list(map(int, fields[:8]))
        assert values[:2] == [face, cp]
        expected = atlases[face]["by_codepoint"].get(cp)
        fallback = expected is None
        if fallback:
            expected = atlases[face]["by_codepoint"][ord('?')]
        assert values[2:] == [expected["width"], expected["height"],
                              expected["safe_bearing_x"], expected["bearing_y"],
                              expected["advance"], int(fallback)]
        assert fields[8] == "".join(expected["rows"]), f"raster differs: face{face} U+{cp:04X}"
        compared_pixels += len(fields[8])
    print(f"Exact source comparison passed: {len(actual)} glyphs / {compared_pixels} pixels")


if __name__ == "__main__":
    main()
