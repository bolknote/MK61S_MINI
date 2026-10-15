#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-basic-graphics.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" \
  "$root/tests/basic_graphics_self_test.cpp" "$root/code/basic_graphics.cpp" -o "$work/raster"
"$work/raster"
bash "$root/tests/run_tinybasic_tests.sh"
MK61_LANGUAGE_VM_TEST=1 bash "$root/tests/run_tinybasic_tests.sh"
