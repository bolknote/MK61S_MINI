#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_resident_firmware_format_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

"${CXX:-clang++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/resident_firmware_format_self_test.cpp" \
  -o "$out"

"$out"
