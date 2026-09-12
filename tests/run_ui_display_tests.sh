#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_ui_display_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for usb in 0 1; do
clang++ -std=c++17 -Wall -Wextra -Werror "${sanitizer_flags[@]}" \
  -DCONFIG -DARDUINO=100 -DMK61_DISPLAY_UC1609=1 \
  -DMK61_PROPORTIONAL_UI_FONTS=1 \
  -DMK61_FIXED_CALCULATOR_FACE=1 \
  -DMK61_HAS_COMPILED_GRAPHICS=1 \
  -DMK61_ENABLE_USB_SCREEN="$usb" -DMK61_ENABLE_EXTENDED_FONT_SETTINGS=1 \
  -DMK61_DEEP_IDLE_ENABLED=1 -DMK61_ANY_FULLSCREEN_FILE=1 \
  -DPIN_GLCD_CD=0 -DPIN_GLCD_RST=1 -DPIN_GLCD_CS=2 \
  -DGLCD_UC1609_BIAS=0 -DGLCD_UC1609_ADDRESS_SET=0 \
  -include "$root/tests/ui_display_shim/panel.hpp" \
  -I"$root/tests/ui_display_shim" -I"$root/code" \
  "$root/tests/ui_display_self_test.cpp" \
  "$root/code/display.cpp" "$root/code/display_ui.cpp" \
  "$root/code/calculator_face.cpp" \
  "$root/code/ui_font.cpp" "$root/code/text_screen.cpp" \
  "$root/code/usb_screen_surface.cpp" \
  "$root/code/builtin_font.cpp" "$root/code/fmk_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" -o "$out"
"$out"
done
