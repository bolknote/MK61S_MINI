#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-sheet-tests.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=(-std=c++17 -O2 -Wall -Wextra -Werror -I"$root/code"
  -I"$root/sdk/portable/include" -I"$root/examples/portable-apps/SHEET")
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ "${flags[@]}" "$root/tests/sheet_engine_self_test.cpp" \
  "$root/examples/portable-apps/SHEET/sheet_engine.cpp" -o "$work/engine"
"$work/engine"
clang++ "${flags[@]}" "$root/tests/sheet_phone_input_self_test.cpp" -o "$work/phone"
"$work/phone"
for keyboard in MINI CLASSIC; do
  clang++ "${flags[@]}" -DARDUINO=100 -DMK61_DISPLAY_UC1609 \
    -DMK61_KEYBOARD_"$keyboard" -I"$root/tests/mk_math_shim" \
    "$root/tests/sheet_app_ui_self_test.cpp" \
    "$root/examples/portable-apps/SHEET/sheet_engine.cpp" \
    "$root/code/builtin_font.cpp" "$root/code/ERM19264_graphics_font.cpp" \
    -o "$work/ui-$keyboard"
  "$work/ui-$keyboard"
done
python3 "$root/tests/sheet_package_self_test.py"
