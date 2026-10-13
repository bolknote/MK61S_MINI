#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_hd44780_controller_self_test"
"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -I"$root/code" "$root/tests/hd44780_controller_self_test.cpp" -o "$out"
"$out"
echo 'HD44780 cold boot and every warm-reset nibble phase: OK'
