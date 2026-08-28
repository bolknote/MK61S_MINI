#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_display_font_self_test"
ws0010_out="${TMPDIR:-/tmp}/mk61_ws0010_markdown_font_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO=100 \
  -DMK61_DISPLAY_UC1609 \
  -I"$root/code" \
  -I"$root/tests/mk_math_shim" \
  "$root/tests/display_font_self_test.cpp" \
  "$root/code/builtin_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" \
  "$root/code/fmk_font.cpp" \
  "$root/code/text_screen.cpp" \
  -o "$out"

"$out" "$@"

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO=100 \
  -DMK61_OLED1602_WS0010 \
  -DMK61_WS0010_GRAPHICS_100X16=1 \
  -DMK61_ENABLE_MARKDOWN_VIEWER=1 \
  -I"$root/code" \
  -I"$root/tests/mk_math_shim" \
  "$root/tests/ws0010_markdown_font_self_test.cpp" \
  "$root/code/builtin_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" \
  -o "$ws0010_out"

"$ws0010_out"
