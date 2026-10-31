#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_loadable_module_format_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for backend in software stm32 words-software words-stm32; do
  backend_flags=()
  if [[ "$backend" == words-* ]]; then
    backend_flags+=(-DMK61_MEMORY_TEST_WORDS)
  fi
  if [[ "$backend" == *stm32 ]]; then
    backend_flags+=(-DMK61_CRC32_EMULATE_STM32)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    "${backend_flags[@]}" \
    -I"$root/code" \
    "$root/tests/loadable_module_format_self_test.cpp" \
    "$root/code/loadable_module_format.cpp" \
    "$root/code/zx0.cpp" \
    -o "$out-$backend"

  "$out-$backend"
done
