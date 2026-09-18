#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_display_font_self_test"
ws0010_out="${TMPDIR:-/tmp}/mk61_ws0010_markdown_font_self_test"
profile_out="${TMPDIR:-/tmp}/mk61_builtin_font_profile_self_test"
prepared_out="${TMPDIR:-/tmp}/mk61_prepared_font_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO=100 \
  -DMK61_DISPLAY_UC1609 \
  -DMK61_PROPORTIONAL_UI_FONTS=1 \
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
  -I"$root/code" \
  "$root/tests/prepared_font_self_test.cpp" \
  "$root/code/fmk_font.cpp" "$root/code/fmk_prepare.cpp" \
  "$root/code/prepared_font.cpp" \
  -o "$prepared_out"

"$prepared_out" \
  "$root/programs/games/High Noon/HighNoon.FMK" \
  "$root/programs/Fonts/DejaVu-12.FMK" \
  "$root/programs/Fonts/DejaVu-14.FMK"

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

for profile in a00 a02 ws0010; do
  profile_flags=()
  case "$profile" in
    a00) profile_flags=(-DMK61_LCD1602_A00) ;;
    a02) profile_flags=(-DMK61_LCD1602_A02) ;;
    ws0010) profile_flags=(-DMK61_OLED1602_WS0010 -DMK61_WS0010_GRAPHICS_100X16=0) ;;
  esac
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    -DARDUINO=100 \
    "${profile_flags[@]}" \
    -I"$root/code" \
    -I"$root/tests/mk_math_shim" \
    "$root/tests/builtin_font_profile_self_test.cpp" \
    "$root/code/builtin_font.cpp" \
    -o "$profile_out"
  "$profile_out"
done
