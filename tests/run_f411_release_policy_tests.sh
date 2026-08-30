#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
matrix="$root/tests/run_f411_release_matrix.sh"
usb_build="$root/tests/run_f411_usb_suspend_compile_check.sh"

bash -n "$matrix"

# The matrix is a release gate, not a synthetic maximum-code-size exercise.
# Keep LTO size-oriented and retain explicit growth room in every F411 image.
grep -Fq 'usb=CDCgen,opt=oslto' "$matrix"
if grep -Fq 'usb=CDCgen,opt=o3lto' "$matrix"; then
  printf 'F411 release matrix must not use the unsafe O3+LTO profile\n' >&2
  exit 1
fi
grep -Eq '^minimum_flash_headroom=[1-9][0-9]*$' "$matrix"
grep -Fq 'unsafe Flash headroom' "$matrix"
grep -Fq 'MK61_REQUIRE_RESIDENT_CRC=1' "$matrix"
grep -Fq 'seal-firmware.sh" seal --max-size 524288' "$matrix"
grep -Fq 'seal-firmware.sh" check --max-size 524288' "$matrix"

# The ordinary mini V3 WS0010 release, not a one-off laboratory define set,
# must carry the qualified USB-preserving STOP path. Other profiles are
# checked for the absence of its strong wake IRQ.
grep -Fq 'check_usb_suspend_elf.sh"' "$matrix"
grep -Fq 'check_usb_suspend_elf.sh" --disabled' "$matrix"
grep -Fq -- '-DMK61_OLED1602_WS0010 -DMK61_REQUIRE_RESIDENT_CRC=1' \
  "$usb_build"
if grep -Eq 'MK61_ENABLE_(DEEP_IDLE|USB_SUSPEND|USB_AUTO_DEEP_IDLE)_QUALIFICATION=1' \
    "$usb_build"; then
  printf 'F411 production STOP check must not depend on laboratory flags\n' >&2
  exit 1
fi
grep -Fq '  256' "$root/tests/run_release_preflight.sh"

printf 'f411_release_policy_tests: ok\n'
