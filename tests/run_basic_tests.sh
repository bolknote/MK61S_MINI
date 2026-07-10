#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_basic_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

basic_enabled="${MK61_ENABLE_BASIC:-1}"

if [[ "$basic_enabled" == "0" ]]; then
  echo "basic_self_test: skipped (MK61_ENABLE_BASIC=0)"
  exit 0
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DBASIC_HOST_TEST \
  -DBASIC_SELF_TEST \
  -DMK61_ENABLE_BASIC="$basic_enabled" \
  -I"$root/code" \
  "$root/tests/basic_self_test.cpp" \
  "$root/code/basic.cpp" \
  -o "$out"

"$out"
