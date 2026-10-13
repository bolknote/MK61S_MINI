#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_usb_stop_wakeup_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for supported in 0 1; do
  for device in 0 1; do
    clang++ -std=c++17 -Wall -Wextra -Werror \
      "${sanitizer_flags[@]}" \
      -DMK61_USB_SUSPEND_SUPPORTED="$supported" -DMK61_TEST_USB_DEVICE="$device" \
      -I"$root/tests/usb_stop_wakeup_shim" -I"$root/code" \
      "$root/tests/usb_stop_wakeup_self_test.cpp" -o "$out-$supported-$device"
    "$out-$supported-$device"
  done
done
python3 "$root/tests/usb_suspend_elf_self_test.py"
