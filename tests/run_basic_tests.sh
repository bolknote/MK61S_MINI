#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_basic_self_test"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -DBASIC_HOST_TEST \
  -DBASIC_SELF_TEST \
  -I"$root/code" \
  "$root/tests/basic_self_test.cpp" \
  "$root/code/basic.cpp" \
  -o "$out"

"$out"
