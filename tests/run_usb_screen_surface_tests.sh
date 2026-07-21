#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_usb_screen_surface_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO=100 \
  -DMK61_ENABLE_USB_SCREEN=1 \
  -I"$root/code" \
  -I"$root/tests/mk_math_shim" \
  "$root/tests/usb_screen_surface_self_test.cpp" \
  "$root/code/usb_screen_surface.cpp" \
  "$root/code/builtin_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" \
  "$root/code/fmk_font.cpp" \
  "$root/code/text_screen.cpp" \
  -o "$out"

"$out"
