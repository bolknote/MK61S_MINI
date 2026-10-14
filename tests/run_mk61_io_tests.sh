#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mktemp -t mk61-io.XXXXXX)"
trap 'rm -f "$out"' EXIT
clang++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I"$root/code" "$root/tests/mk61_io_self_test.cpp" "$root/code/mk61_io.cpp" -o "$out"
"$out"
