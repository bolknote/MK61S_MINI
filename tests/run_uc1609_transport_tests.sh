#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_uc1609_transport_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for native in 0 1; do
  native_flags=()
  if [[ "$native" == "1" ]]; then
    native_flags=(-DMK61_NATIVE_RUNTIME=1 -DPIN_GLCD_CD=1 -DPIN_GLCD_RST=2 -DPIN_GLCD_CS=3)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" "${native_flags[@]}" \
    -DARDUINO=10800 \
    -DARDUINO_ARCH_STM32 \
    -DCONFIG \
    -DMK61_DISPLAY_UC1609 \
    -DMK61_ENABLE_SPI1_ARBITER=1 \
    -I"$root/tests/uc1609_transport_shim" \
    -I"$root/code" \
    "$root/tests/uc1609_transport_self_test.cpp" \
    "$root/code/ERM19264_UC1609.cpp" \
    "$root/code/spi1_bus.cpp" \
    -o "$out"

  "$out"
done
