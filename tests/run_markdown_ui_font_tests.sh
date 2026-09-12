#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
font_bridge_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-md-font.XXXXXX")"
trap 'rm -f "$font_bridge_dir/builtin" "$font_bridge_dir/portable"; rmdir "$font_bridge_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for mode in builtin portable; do
  mode_flags=()
  if [[ "$mode" == portable ]]; then mode_flags=(-DMK61_BUILD_PORTABLE_SYSTEM); fi
  clang++ -std=c++17 -Wall -Wextra -Werror -pedantic \
    "${sanitizer_flags[@]}" "${mode_flags[@]}" -DARDUINO=100 -DMK61_DISPLAY_UC1609 \
    -DMK61_PROPORTIONAL_UI_FONTS=1 \
    -I"$root/code" -I"$root/tests/mk_math_shim" \
    "$root/tests/markdown_ui_font_self_test.cpp" "$root/code/ui_font.cpp" \
    "$root/code/fmk_font.cpp" \
    -o "$font_bridge_dir/$mode"
  "$font_bridge_dir/$mode"
done
