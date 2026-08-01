#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_spi1_dma_self_test"

"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -I"$root/code" \
  "$root/code/spi1_dma.cpp" \
  "$root/tests/spi1_dma_self_test.cpp" \
  -o "$out"

"$out"
