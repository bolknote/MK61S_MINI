#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_tinybasic_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

tinybasic_enabled="${MK61_ENABLE_TINYBASIC:-}"
if [[ -z "$tinybasic_enabled" ]]; then
  if grep -Eq '^[[:space:]]*#[[:space:]]*define[[:space:]]+MK61_ENABLE_TINYBASIC[[:space:]]+0([[:space:]]|$)' "$root/code/config.h"; then
    tinybasic_enabled=0
  else
    tinybasic_enabled=1
  fi
fi

if [[ "$tinybasic_enabled" == "0" ]]; then
  echo "tinybasic_self_test: skipped (MK61_ENABLE_TINYBASIC=0)"
  exit 0
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DTINYBASIC_HOST_TEST \
  -DTINYBASIC_SELF_TEST \
  -DMK61_ENABLE_TINYBASIC="$tinybasic_enabled" \
  -I"$root/code" \
  "$root/tests/tinybasic_self_test.cpp" \
  "$root/code/tinybasic.cpp" \
  -o "$out"

"$out"
