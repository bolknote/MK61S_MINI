#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
CXX=${CXX:-c++}
FLAGS=(-std=c++17 -Wall -Wextra -Werror -I"$root/code")

if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  FLAGS+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

"$CXX" "${FLAGS[@]}" "$root/tests/spi_nor_sfdp_self_test.cpp" \
  -o /tmp/mk61_spi_nor_sfdp_self_test
/tmp/mk61_spi_nor_sfdp_self_test
