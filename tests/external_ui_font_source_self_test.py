#!/usr/bin/env python3
"""Keep the shipped DejaVu FMKs in sync with their reviewed native atlases."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_fmk_from_ui_atlas import encode  # noqa: E402
from m8_codec import SPECIAL_TO_BYTE  # noqa: E402


def main() -> None:
    required = {ord(char) for char in SPECIAL_TO_BYTE}
    for size, gap in ((12, 1), (14, 2)):
        source = ROOT / f"tools/.fmk-font/external-fonts/dejavu-{size}.json"
        target = ROOT / f"programs/Fonts/DejaVu-{size}.FMK"
        atlas = json.loads(source.read_text(encoding="utf-8"))
        glyphs = {glyph["codepoint"]: glyph for glyph in atlas["glyphs"]}
        assert len(atlas["glyphs"]) == len(glyphs) == 181
        assert required <= glyphs.keys()
        assert all(any("1" in row for row in glyphs[cp]["rows"])
                   for cp in required)
        assert encode(atlas, gap) == target.read_bytes(), target
    print("DejaVu native M8 rasters and FMK2 packages: ok")


if __name__ == "__main__":
    main()
