#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_focal_self_test"

focal_enabled="${MK61_ENABLE_FOCAL:-}"
if [[ -z "$focal_enabled" ]]; then
  if grep -Eq '^[[:space:]]*#[[:space:]]*define[[:space:]]+MK61_ENABLE_FOCAL[[:space:]]+0([[:space:]]|$)' "$root/code/config.h"; then
    focal_enabled=0
  else
    focal_enabled=1
  fi
fi

if [[ "$focal_enabled" == "0" ]]; then
  echo "focal_self_test: skipped (MK61_ENABLE_FOCAL=0)"
  exit 0
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  -DFOCAL_HOST_TEST \
  -DFOCAL_SELF_TEST \
  -DMK61_ENABLE_FOCAL="$focal_enabled" \
  -I"$root/code" \
  "$root/tests/focal_self_test.cpp" \
  "$root/code/focal.cpp" \
  -o "$out"

"$out"
