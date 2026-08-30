#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_usb_cdc_rx_guard_self_test"

"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -I"$root/code" \
  "$root/code/usb_cdc_rx_guard.cpp" \
  "$root/tests/usb_cdc_rx_guard_self_test.cpp" \
  -o "$out"

"$out"

linker_flag='--wrap=USBD_CDC_ClearBuffer'
for builder in \
  "$root/tools/.mk61-firmware/mk61-firmware.sh" \
  "$root/tools/.mk61-firmware/mk61-firmware.ps1" \
  "$root/tools/build_f401_bundle.sh" \
  "$root/tests/run_f411_release_matrix.sh" \
  "$root/tests/run_f401_uc1609_compile_check.sh"; do
  grep -Fq -- "$linker_flag" "$builder"
done

cmake="$root/tools/.mk61-gcc/CMakeLists.txt"
grep -Fq -- 'LINKER:--wrap=USBD_CDC_ClearBuffer' "$cmake"
grep -Fq -- 'USBDevice/src/cdc/usbd_cdc.c' "$cmake"
grep -Fq -- 'PROPERTIES COMPILE_OPTIONS "-fno-lto"' "$cmake"
