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


def main():
    atlases, repertoire = generator.load_atlases()
    actual = subprocess.check_output([sys.argv[1], "--dump"], text=True).splitlines()
    assert len(actual) == len(repertoire) * len(atlases)
    compared_pixels = 0
    for line, (face, cp) in zip(actual, ((i, cp) for i in range(4) for cp in repertoire)):
        fields = line.split()
        assert len(fields) == 9
        values = list(map(int, fields[:8]))
        assert values[:2] == [face, cp]
        expected = atlases[face]["by_codepoint"].get(cp)
        fallback = expected is None
        if fallback:
            expected = atlases[face & 1]["by_codepoint"][cp]
        assert values[2:] == [expected["width"], expected["height"],
                              expected["safe_bearing_x"], expected["bearing_y"],
                              expected["advance"], int(fallback)]
        assert fields[8] == "".join(expected["rows"]), f"raster differs: face{face} U+{cp:04X}"
        compared_pixels += len(fields[8])
    print(f"Exact source comparison passed: {len(actual)} glyphs / {compared_pixels} pixels")


if __name__ == "__main__":
    main()
