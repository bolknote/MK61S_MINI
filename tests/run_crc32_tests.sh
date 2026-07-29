#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_crc32_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for backend in software stm32; do
  backend_flags=()
  if [[ "$backend" == "stm32" ]]; then
    backend_flags=(-DMK61_CRC32_EMULATE_STM32)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    "${backend_flags[@]}" \
    -I"$root/code" \
    "$root/tests/crc32_self_test.cpp" \
    -o "$out-$backend"
  "$out-$backend"
done
