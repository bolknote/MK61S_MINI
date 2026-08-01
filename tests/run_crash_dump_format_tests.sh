#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_crash_dump_format_self_test"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/tests/crash_dump_format_self_test.cpp" \
  "$root/code/crash_dump_format.cpp" \
  -o "$out"

"$out"
