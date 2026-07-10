#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_debug_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO=100 \
  -I"$root/code" \
  -I"$root/tests/mk_math_shim" \
  "$root/tests/debug_self_test.cpp" \
  "$root/code/debug.cpp" \
  -o "$out"

"$out"
