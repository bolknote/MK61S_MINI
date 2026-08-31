#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
matrix="$root/tests/run_f411_release_matrix.sh"
usb_build="$root/tests/run_f411_usb_suspend_compile_check.sh"
budgets="$root/tests/release_ram_budgets.sh"
ram_check="$root/tests/check_release_ws0010_ram.sh"
preflight="$root/tests/run_release_preflight.sh"
workflow="$root/.github/workflows/firmware-release.yml"

bash -n "$matrix"
bash -n "$usb_build"
bash -n "$budgets"
bash -n "$ram_check"
bash -n "$preflight"
source "$budgets"

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

# Both ordinary qualified releases, not one-off laboratory define sets, must
# carry the USB-preserving STOP path. Other profiles are checked for the
# absence of its strong wake IRQ.
grep -Fq 'check_usb_suspend_elf.sh"' "$matrix"
grep -Fq 'check_usb_suspend_elf.sh" --disabled' "$matrix"
grep -Fq "compile_profile ws0010 '-DMK61_OLED1602_WS0010'" "$usb_build"
grep -Fq "compile_profile classic-v3-uc1609 '-DMK61_BOARD_CLASSIC_V3'" \
  "$usb_build"
if grep -Eq 'MK61_ENABLE_(DEEP_IDLE|USB_SUSPEND|USB_AUTO_DEEP_IDLE)_QUALIFICATION=1' \
    "$usb_build"; then
  printf 'F411 production STOP check must not depend on laboratory flags\n' >&2
  exit 1
fi
# Local preflight and GitHub Actions must consume the same explicit budgets.
# This policy test runs in the short host job, before the expensive firmware
# matrix, so a duplicated or omitted CI argument cannot escape local testing.
[[ "$MK61_F401_WS0010_MAX_RAM_GROWTH" == 0 ]]
[[ "$MK61_F411_WS0010_MAX_RAM_GROWTH" == 256 ]]
[[ "$MK61_F401_WS0010_USB_MAX_RAM_GROWTH" == 0 ]]
[[ "$MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH" == 0 ]]
grep -Fq 'source "$root/tests/release_ram_budgets.sh"' "$ram_check"
for variable in \
  MK61_F401_WS0010_MAX_RAM_GROWTH \
  MK61_F411_WS0010_MAX_RAM_GROWTH \
  MK61_F401_WS0010_USB_MAX_RAM_GROWTH \
  MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH; do
  grep -Fq "$variable" "$ram_check"
done
grep -Fq 'check_release_ws0010_ram.sh" "$size_tool"' "$preflight"
grep -Fq 'check_release_ws0010_ram.sh "$size_tool"' "$workflow"
if grep -Fq 'check_ws0010_ram.sh' "$preflight" || \
   grep -Fq 'check_ws0010_ram.sh' "$workflow"; then
  printf 'Release entry points must use the shared WS0010 RAM checker\n' >&2
  exit 1
fi
[[ "$(grep -Fc '"$root/tests/check_ws0010_ram.sh"' "$ram_check")" -eq 4 ]]
grep -Fq 'name: Enforce WS0010 RAM budgets' "$workflow"
if grep -Fq 'Enforce zero-RAM-cost WS0010 profile' "$workflow"; then
  printf 'GitHub workflow still claims a zero-cost F411 WS0010 profile\n' >&2
  exit 1
fi

printf 'f411_release_policy_tests: ok\n'
