#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_usb_screen_surface_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for panel in uc1609 uc1609-shared lcd1602; do
panel_flags=(-DMK61_DISPLAY_UC1609=1 -DMK61_PROPORTIONAL_UI_FONTS=1)
if [[ "$panel" == uc1609-shared ]]; then panel_flags+=(-DMK61_SHARED_SCREEN_GRID=1); fi
if [[ "$panel" == lcd1602 ]]; then
  panel_flags=(-DMK61_LCD1602_A00 -DMK61_PROPORTIONAL_UI_FONTS=0)
fi
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO=100 \
  -DMK61_ENABLE_USB_SCREEN=1 \
  "${panel_flags[@]}" \
  -DMK61_FIXED_CALCULATOR_FACE=0 \
  -I"$root/code" \
  -I"$root/tests/mk_math_shim" \
  "$root/tests/usb_screen_surface_self_test.cpp" \
  "$root/code/usb_screen_surface.cpp" \
  "$root/code/ui_text_renderer.cpp" \
  "$root/code/ui_font.cpp" \
  "$root/code/builtin_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" \
  "$root/code/fmk_font.cpp" \
  "$root/code/prepared_font.cpp" \
  "$root/code/text_screen.cpp" \
  -o "$out"

"$out"
done

for proportional in 0 1; do
  clang++ -std=c++17 -Wall -Wextra -Werror "${sanitizer_flags[@]}" \
    -DCONFIG -DMK61_PROPORTIONAL_UI_FONTS="$proportional" \
    -DMK61_DISPLAY_UC1609=1 -I"$root/code" \
    "$root/tests/text_screen_shared_self_test.cpp" "$root/code/text_screen.cpp" \
    -o "$out-grid"
  "$out-grid"
done
