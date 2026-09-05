#!/usr/bin/env python3
"""Compile selected production UI bodies against a recording host surface.

No renderer or copy of menu algorithms lives in tests. Selection fails closed
on a removed/renamed function; #line diagnostics point to the production file.
The generated .inc files live only in the test temp directory.
"""
import re
import sys
from pathlib import Path

TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/|[{}]')


def body(path: Path, marker: str, semicolon: bool = False) -> str:
    source = path.read_text()
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for match in TOKENS.finditer(source, opening):
        if match[0] == "{":
            depth += 1
        elif match[0] == "}":
            depth -= 1
            if depth == 0:
                end = match.end() + int(semicolon)
                line = source[:start].count("\n") + 1
                return f'#line {line} "{path}"\n' + source[start:end] + "\n"
    raise ValueError(f"unterminated production body: {path}: {marker}")


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "code"
    out = Path(sys.argv[1])
    (out / "ui_geometry.inc").write_text(body(root / "display.hpp", "namespace lcd_display {"))
    menu = root / "menu.cpp"
    pieces = ["namespace library_mk61 {\n"]
    for marker in ["static bool sameTextProfile(", "static const char* fontPresetName(", "static lcd_display::TextProfile nextFontPreset("]:
        pieces.append(body(menu, marker))
    pieces += ["}\nusing library_mk61::sameTextProfile;\n", body(menu, "enum class FontSetupPhase", True)]
    for marker in ["static void noteFontSetupPhase(", "static void formatFontSetupLine(", "static void printFontSetupLine(", "static void drawFontSetup(", "static void applyFontSetupProfile("]:
        pieces.append(body(menu, marker))
    (out / "ui_menu.inc").write_text("\n".join(pieces))


if __name__ == "__main__":
    main()
