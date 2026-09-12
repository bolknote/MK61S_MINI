#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
if ! pkg-config --exists freetype2; then
  echo "fmk_converter_test: skipped (FreeType unavailable)"
  exit 0
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-fmk-converter.XXXXXX")"
trap 'rm -rf "$work"' EXIT HUP INT TERM
mono="$work/mono.fmk"
proportional="$work/proportional.fmk"
thin="$work/thin.fmk"
thin_warnings="$work/thin-warnings.txt"
help="$work/help.txt"
"$root/tools/build_fmk_font.sh" >"$help" 2>&1
grep -q '^usage: fmk_font INPUT OUTPUT' "$help"
grep -q -- '--max-file-size N' "$help"
"$root/tools/build_fmk_font.sh" "$root/tests/data/fmk_test.bdf" "$mono" --cell 5x8 --size 8 --chars AB --compression auto
"$root/tools/build_fmk_font.sh" "$root/tests/data/fmk_test.bdf" "$proportional" --cell 8x12 --size 8 --chars AB --proportional --compression auto
"$root/tools/build_fmk_font.sh" "$root/tests/data/fmk_thin_test.bdf" "$thin" --cell 5x8 --size 32 --chars '1+' --compression auto 2>"$thin_warnings"
test -x "$root/.build/tools/fmk_font"
test ! -e "$root/tools/fmk_font"
grep -q 'font is missing.*U+002B' "$thin_warnings"
"$root/tests/run_display_font_tests.sh" "$mono" >/dev/null
"$root/tests/run_display_font_tests.sh" "$proportional" >/dev/null
"$root/tests/run_display_font_tests.sh" "$thin" --require-ink >/dev/null

# The production UI now comes from native bitmap strikes. Exercise the exact
# exporter branch with a tiny BDF fixture so a future refactor cannot silently
# re-enable scaling or lose baseline/advance preservation.
preview="$work/font-preview"
preview_json="$work/font-preview.json"
read -r -a freetype_cflags <<<"$(pkg-config --cflags freetype2)"
read -r -a freetype_libs <<<"$(pkg-config --libs freetype2)"
clang++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  "${freetype_cflags[@]}" "$root/tools/.fmk-font/font_preview.cpp" \
  "${freetype_libs[@]}" -o "$preview"
"$preview" "$root/tests/data/fmk_test.bdf" "$preview_json" \
  --height 8 --encoding cp1251 >/dev/null
python3 "$root/tests/font_preview_bitmap_self_test.py" "$preview_json"

# Keep the old 1536-byte target as the converter default, but prove that an
# explicitly targeted F411 package can use the whole existing 8 KiB BULK
# arena. The generated BDF is deterministic and needs no host font package.
large_bdf="$work/large.bdf"
large_rejected="$work/large-rejected.txt"
large_fmk="$work/large.fmk"
{
  printf '%s\n' 'STARTFONT 2.1' 'FONT -mk61-test-medium-r-normal--16-160-75-75-c-160-iso10646-1' \
    'SIZE 16 75 75' 'FONTBOUNDINGBOX 16 16 0 0' 'STARTPROPERTIES 2' \
    'FONT_ASCENT 16' 'FONT_DESCENT 0' 'ENDPROPERTIES' 'CHARS 95'
  for cp in $(seq 32 126); do
    printf 'STARTCHAR U+%04X\nENCODING %u\nSWIDTH 1000 0\nDWIDTH 16 0\nBBX 16 16 0 0\nBITMAP\n' "$cp" "$cp"
    for _ in $(seq 1 16); do printf '%s\n' 'A55A'; done
    printf '%s\n' 'ENDCHAR'
  done
  printf '%s\n' 'ENDFONT'
} >"$large_bdf"
if "$root/tools/build_fmk_font.sh" "$large_bdf" "$large_fmk" \
    --cell 16x16 --size 16 --chars ascii --compression none \
    >"$large_rejected" 2>&1; then
  echo 'Default FMK converter unexpectedly accepted an F411-sized file' >&2
  exit 1
fi
grep -q 'selected firmware limit' "$large_rejected"
"$root/tools/build_fmk_font.sh" "$large_bdf" "$large_fmk" \
  --cell 16x16 --size 16 --chars ascii --compression none \
  --max-file-size 8192 >/dev/null
test "$(wc -c <"$large_fmk")" -gt 1536
test "$(wc -c <"$large_fmk")" -le 8192
"$root/tests/run_display_font_tests.sh" "$large_fmk" >/dev/null
echo "fmk_converter_test: ok"
