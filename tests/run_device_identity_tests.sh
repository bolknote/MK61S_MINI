#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_device_identity_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/device_identity_self_test.cpp" \
  "$root/code/device_identity.cpp" \
  -o "$out"

"$out"

# CDC and MSC must expose the same UID-derived serial.  A fixed MSC serial
# makes two simultaneously connected calculators indistinguishable to host
# caches and defeats the identity/topology safeguards in the HIL runner.
grep -q 'device_identity::format_stm32duino_usb_serial' \
  "$root/code/usb_mass_storage.cpp"
if grep -q 'static const u8 serial_desc' "$root/code/usb_mass_storage.cpp"; then
  echo "usb_mass_storage.cpp must not contain a fixed serial descriptor" >&2
  exit 1
fi
