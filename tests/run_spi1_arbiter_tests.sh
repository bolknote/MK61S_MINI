#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

flags=(-std=c++17 -Wall -Wextra -Werror)
if [[ "${MK61_SANITIZE:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ "${flags[@]}" \
  -I"$root/code" \
  "$root/tests/spi1_arbiter_self_test.cpp" \
  -o "$work/spi1_arbiter_self_test"

"$work/spi1_arbiter_self_test"

clang++ "${flags[@]}" \
  -DMK61_ENABLE_SPI1_ARBITER=1 \
  -I"$root/code" \
  "$root/code/spi1_bus.cpp" \
  "$root/tests/spi1_bus_self_test.cpp" \
  -o "$work/spi1_bus_enabled_self_test"

"$work/spi1_bus_enabled_self_test"

clang++ "${flags[@]}" \
  -DMK61_ENABLE_SPI1_ARBITER=0 \
  -I"$root/code" \
  "$root/code/spi1_bus.cpp" \
  "$root/tests/spi1_bus_self_test.cpp" \
  -o "$work/spi1_bus_disabled_self_test"

"$work/spi1_bus_disabled_self_test"
