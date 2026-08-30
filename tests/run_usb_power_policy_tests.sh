#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_usb_power_policy_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/usb_power_policy_self_test.cpp" \
  -o "$out"
"$out"

wrappers=(
  USBD_LL_SetupStage
  USBD_LL_Reset
  USBD_LL_Suspend
  USBD_LL_Resume
  USBD_LL_DevConnected
  USBD_LL_DevDisconnected
)
builders=(
  "$root/tools/.mk61-firmware/mk61-firmware.sh"
  "$root/tools/.mk61-firmware/mk61-firmware.ps1"
  "$root/tools/build_f401_bundle.sh"
  "$root/tests/run_f411_release_matrix.sh"
  "$root/tests/run_f401_uc1609_compile_check.sh"
)
for wrapper in "${wrappers[@]}"; do
  for builder in "${builders[@]}"; do
    grep -Fq -- "--wrap=$wrapper" "$builder"
  done
  grep -Fq -- "LINKER:--wrap=$wrapper" \
    "$root/tools/.mk61-gcc/CMakeLists.txt"
done
