#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_ui_display_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for variant in physical legacy-usb shared-usb physical-loan; do
usb=1
shared_grid=0
if [[ "$variant" == physical ]]; then usb=0; fi
if [[ "$variant" == shared-usb ]]; then shared_grid=1; fi
loan="$shared_grid"
if [[ "$variant" == physical-loan ]]; then usb=0; loan=1; fi
clang++ -std=c++17 -Wall -Wextra -Werror "${sanitizer_flags[@]}" \
  -DCONFIG -DARDUINO=100 -DMK61_DISPLAY_UC1609=1 \
  -DMK61_PROPORTIONAL_UI_FONTS=1 \
  -DMK61_FIXED_CALCULATOR_FACE=1 \
  -DMK61_HAS_COMPILED_GRAPHICS=1 \
  -DMK61_ENABLE_USB_SCREEN="$usb" -DMK61_ENABLE_EXTENDED_FONT_SETTINGS=1 \
  -DMK61_SHARED_SCREEN_GRID="$shared_grid" -DMK61_SCREEN_BUFFER_LOAN="$loan" \
  -DMK61_DEEP_IDLE_ENABLED=1 -DMK61_ANY_FULLSCREEN_FILE=1 \
  -DPIN_GLCD_CD=0 -DPIN_GLCD_RST=1 -DPIN_GLCD_CS=2 \
  -DGLCD_UC1609_BIAS=0 -DGLCD_UC1609_ADDRESS_SET=0 \
  -include "$root/tests/ui_display_shim/panel.hpp" \
  -I"$root/tests/ui_display_shim" -I"$root/code" \
  "$root/tests/ui_display_self_test.cpp" \
  "$root/code/display.cpp" "$root/code/display_ui.cpp" \
  "$root/code/display_buffer_loan.cpp" \
  "$root/code/disk_activity.cpp" \
  "$root/code/ui_text_renderer.cpp" \
  "$root/code/calculator_face.cpp" \
  "$root/code/ui_font.cpp" "$root/code/text_screen.cpp" \
  "$root/code/usb_screen_surface.cpp" \
  "$root/code/builtin_font.cpp" "$root/code/fmk_font.cpp" \
  "$root/code/fmk_prepare.cpp" "$root/code/prepared_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" -o "$out"
"$out"
done

# Character displays must not carry the animation, glyphs, state, or polling
# calls when the virtual graphical screen is disabled, including WS0010.
for panel in MK61_LCD1602_A00 MK61_LCD1602_A02 MK61_OLED1602_WS0010; do
  clang++ -std=c++17 -Wall -Wextra -Werror -DARDUINO=100 \
    -D"$panel" -DMK61_ENABLE_USB_SCREEN=0 \
    -I"$root/code" -I"$root/tests/mk_math_shim" \
    -c "$root/code/disk_activity.cpp" -o "$out-no-graphics.o"
  if nm "$out-no-graphics.o" | grep -Eq 'disk_activity|DiskActivity|DiskSaving'; then
    echo "Unexpected disk animation in $panel without USB Screen" >&2
    exit 1
  fi
done
echo "Disk animation excluded from A00/A02/WS0010 without USB Screen"
