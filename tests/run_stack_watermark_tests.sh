#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_stack_watermark_self_test"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/tests/stack_watermark_self_test.cpp" \
  -o "$out"
"$out"
rm -f "$out"
