#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mktemp -d "${TMPDIR:-/tmp}/mk61-ui-contract.XXXXXX")"
trap 'rm -rf "$out"' EXIT
python3 "$root/tests/ui_contract_surface.py" "$out"
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for extended in 0 1; do
  clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_DISPLAY_UC1609=1 -DMK61_HAS_GRAPHICAL_TEXT_SETTINGS=1 \
    -DMK61_ENABLE_USB_SCREEN=0 -DMK61_ENABLE_EXTENDED_FONT_SETTINGS="$extended" \
    -I"$out" -I"$root/code" "$root/tests/ui_contract_self_test.cpp" \
    "$root/code/virtual_fat_diagnostic.cpp" "$root/code/markdown_document.cpp" \
    "$root/code/markdown_plain.cpp" -o "$out/ui-contract"
  "$out/ui-contract"
done
