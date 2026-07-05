#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_basic_self_test"

basic_enabled="${MK61_ENABLE_BASIC:-}"
if [[ -z "$basic_enabled" ]]; then
  if grep -Eq '^[[:space:]]*#[[:space:]]*define[[:space:]]+MK61_ENABLE_BASIC[[:space:]]+0([[:space:]]|$)' "$root/code/config.h"; then
    basic_enabled=0
  else
    basic_enabled=1
  fi
fi

if [[ "$basic_enabled" == "0" ]]; then
  echo "basic_self_test: skipped (MK61_ENABLE_BASIC=0)"
  exit 0
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  -DBASIC_HOST_TEST \
  -DBASIC_SELF_TEST \
  -DMK61_ENABLE_BASIC="$basic_enabled" \
  -I"$root/code" \
  "$root/tests/basic_self_test.cpp" \
  "$root/code/basic.cpp" \
  -o "$out"

"$out"
