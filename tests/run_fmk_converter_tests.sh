#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
if ! pkg-config --exists freetype2; then
  echo "fmk_converter_test: skipped (FreeType unavailable)"
  exit 0
fi

mono="${TMPDIR:-/tmp}/mk61_fmk_mono.fmk"
proportional="${TMPDIR:-/tmp}/mk61_fmk_proportional.fmk"
help="${TMPDIR:-/tmp}/mk61_fmk_help.txt"
"$root/tools/build_fmk_font.sh" >"$help" 2>&1
grep -q '^usage: fmk_font INPUT OUTPUT' "$help"
"$root/tools/build_fmk_font.sh" "$root/tests/data/fmk_test.bdf" "$mono" --cell 5x8 --size 8 --chars AB --compression auto
"$root/tools/build_fmk_font.sh" "$root/tests/data/fmk_test.bdf" "$proportional" --cell 8x12 --size 8 --chars AB --proportional --compression auto
"$root/tests/run_display_font_tests.sh" "$mono" >/dev/null
"$root/tests/run_display_font_tests.sh" "$proportional" >/dev/null
echo "fmk_converter_test: ok"
