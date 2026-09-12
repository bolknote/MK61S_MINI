#!/usr/bin/env python3
"""Verify that font_preview preserves an unscaled native BDF strike."""

import json
from pathlib import Path
import sys


def main() -> None:
    atlas = json.loads(Path(sys.argv[1]).read_text())
    assert atlas["schema"] == 1
    assert atlas["rasterizer"] == \
        "FreeType native bitmap strike; empty border cropped"
    assert (atlas["target_height"], atlas["ppem"]) == (8, 8)
    assert (atlas["ascent"], atlas["descent"], atlas["height"]) == (7, 0, 7)
    assert len(atlas["missing"]) == 167
    assert atlas["glyphs"] == [
        {
            "codepoint": 65,
            "width": 5,
            "height": 7,
            "bearing_x": 0,
            "bearing_y": 7,
            "safe_bearing_x": 0,
            "native_advance": 6,
            "advance": 6,
            "rows": [
                "01110", "10001", "10001", "11111",
                "10001", "10001", "10001",
            ],
        },
        {
            "codepoint": 66,
            "width": 5,
            "height": 7,
            "bearing_x": 0,
            "bearing_y": 7,
            "safe_bearing_x": 0,
            "native_advance": 6,
            "advance": 6,
            "rows": [
                "11110", "10001", "10001", "11110",
                "10001", "10001", "11110",
            ],
        },
    ]
    print("font_preview native bitmap strike: ok")


if __name__ == "__main__":
    main()
