#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_program_load_self_test"
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -I"$root/code" \
  "$root/tests/program_load_self_test.cpp" \
  "$root/code/program_load.cpp" "$root/code/zx0_stream.cpp" \
  "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" -o "$out"
"$out"
