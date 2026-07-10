#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_m61_text_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DM61_TEXT_HOST_TEST \
  -I"$root/code" \
  "$root/tests/m61_text_self_test.cpp" \
  "$root/code/m61_text.cpp" \
  -o "$out"

"$out"
