#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_uc1609_transport_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO=10800 \
  -DARDUINO_ARCH_STM32 \
  -DCONFIG \
  -DMK61_DISPLAY_UC1609 \
  -I"$root/tests/uc1609_transport_shim" \
  -I"$root/code" \
  "$root/tests/uc1609_transport_self_test.cpp" \
  "$root/code/ERM19264_UC1609.cpp" \
  -o "$out"

"$out"
