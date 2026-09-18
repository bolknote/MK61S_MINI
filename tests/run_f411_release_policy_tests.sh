#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
matrix="$root/tests/run_f411_release_matrix.sh"
o3_build="$root/tests/run_f411_o3_compile_check.sh"
stock_linker_build="$root/tests/run_stock_linker_compile_check.sh"
usb_build="$root/tests/run_f411_usb_suspend_compile_check.sh"
f401_matrix="$root/tests/run_f401_release_matrix.sh"
budgets="$root/tests/release_ram_budgets.sh"
ram_check="$root/tests/check_release_ws0010_ram.sh"
preflight="$root/tests/run_release_preflight.sh"
core_check="$root/tests/check_core_native_hot_paths_elf.sh"
workflow="$root/.github/workflows/firmware-release.yml"
contract="$root/tools/release_contract.py"
mixed_policy="$root/code/firmware_optimization.hpp"
config="$root/code/config.h"
hot_core="$root/code/mk61emu_core.cpp"

for script in "$matrix" "$o3_build" "$stock_linker_build" "$usb_build" "$f401_matrix" "$budgets" \
    "$ram_check" "$preflight" "$core_check"; do
  bash -n "$script"
done
python3 "$contract" validate >/dev/null
source "$budgets"

require_equal() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" != "$expected" ]]; then
    printf '%s: expected %s, got %s\n' "$label" "$expected" "$actual" >&2
    exit 1
  fi
}

require_equal f411_release_case_count \
  "$(python3 "$contract" cases --group f411-release --format count)" 16
require_equal f411_stop_case_count \
  "$(python3 "$contract" cases --group f411-stop --format count)" 2
require_equal f401_product_case_count \
  "$(python3 "$contract" cases --group f401-product --format count)" 5
require_equal f401_capability_case_count \
  "$(python3 "$contract" cases --group f401-capability --format count)" 4

# Matrix mechanics and policy come from one data source.  The scripts retain
# implementation, never a second list of profiles, defines or budgets.
grep -Fq 'cases --group f411-release --format tsv' "$matrix"
grep -Fq 'cases --group f411-stop --format tsv' "$usb_build"
grep -Fq 'cases --group "$group" --format tsv' "$f401_matrix"
grep -Fq 'resource-report' "$matrix"
grep -Fq 'resource-report' "$usb_build"
grep -Fq 'aggregate-reports' "$f401_matrix"
grep -Fq 'MK61_REQUIRE_RESIDENT_CRC=1' "$matrix"
grep -Fq 'analyze_stack_usage.py' "$matrix"
grep -Fq 'shipping_artifact=untouched' "$root/tests/analyze_stack_usage.py"
if grep -Eq '^compile_variant [a-z0-9]' "$matrix" ||
   grep -Eq '^compile_profile [a-z0-9]' "$usb_build"; then
  printf 'release scripts still contain a hand-written case list\n' >&2
  exit 1
fi
if grep -Fq 'usb=CDCgen,opt=o3lto' "$matrix"; then
  printf 'F411 release matrix must not use the unsafe O3+LTO profile\n' >&2
  exit 1
fi
grep -Fq 'usb=CDCgen,opt=o3std' "$o3_build"
grep -Fq 'MK61_REQUIRE_MIXED_OPTIMIZATION=1' "$o3_build"
grep -Fq 'minimum_headroom=65536' "$o3_build"
grep -Fq 'BLACKPILL_F401CC' "$stock_linker_build"
grep -Fq 'BLACKPILL_F411CE' "$stock_linker_build"
grep -Fq 'opt=oslto' "$stock_linker_build"
grep -Fq '__mk61_dynamic_begin/end references under LTO' "$stock_linker_build"
grep -Fq '#include "firmware_optimization.hpp"' "$config"
grep -Fq '#pragma GCC optimize ("Os")' "$mixed_policy"
grep -Fq '#pragma GCC reset_options' "$hot_core"
grep -Fq 'MK61_REQUIRE_F401_SELECTIVE_O3' "$mixed_policy"
grep -Fq 'MK61_REQUIRE_F411_SELECTIVE_O3' "$mixed_policy"
grep -Fq 'MK61_CORE_HOT_O3 __attribute__((optimize("O3")))' "$mixed_policy"
grep -Fq 'MK61_CORE_HOT_O3 cycle(void)' "$hot_core"
grep -Fq 'MK61_CORE_HOT_O3 __attribute__((noinline, aligned(16)))' \
  "$hot_core"
grep -Fq '#ifndef MK61_F401_PRODUCT_BUILD' "$mixed_policy"
grep -Fq 'MK61_REQUIRE_F411_SELECTIVE_O3=1' "$matrix"
grep -Fq 'MK61_REQUIRE_F411_SELECTIVE_O3=1' "$usb_build"
grep -Fq 'MK61_REQUIRE_F401_SELECTIVE_O3=1' \
  "$root/tests/run_f401_uc1609_compile_check.sh"
grep -Fq 'MK61_REQUIRE_F401_SELECTIVE_O3=1' \
  "$root/tools/.mk61-gcc/CMakeLists.txt"
grep -Fq 'MK61_F401_PRODUCT_BUILD=$product' \
  "$root/tests/run_f401_uc1609_compile_check.sh"
grep -Fq 'check_core_native_hot_paths_elf.sh" "$elf"' "$f401_matrix"
grep -Fq 'check_core_native_hot_paths_elf.sh" --disabled "$elf"' \
  "$f401_matrix"
grep -Fq 'check_core_native_hot_paths_elf.sh' "$matrix"
grep -Fq 'check_core_native_hot_paths_elf.sh' "$o3_build"
grep -Fq 'portable-layout.py' "$o3_build"
grep -Fq 'portable-layout.py' "$usb_build"

# Production STOP is selected by expected behavior in the manifest, not by a
# second board-definition ladder in shell.
grep -Fq 'expect_usb_suspend' "$matrix"
grep -Fq 'expect_ws0010_graphics' "$matrix"
grep -Fq 'check_usb_suspend_elf.sh" --disabled' "$matrix"
grep -Fq 'check_ws0010_graphics_elf.sh" --disabled' "$matrix"
if grep -Eq 'MK61_ENABLE_(DEEP_IDLE|USB_SUSPEND|USB_AUTO_DEEP_IDLE)_QUALIFICATION=1' \
    "$usb_build"; then
  printf 'F411 production STOP check must not depend on laboratory flags\n' >&2
  exit 1
fi

# The compatibility variables are populated from the manifest and must keep
# the already qualified numeric contracts.
require_equal MK61_F401_WS0010_MAX_RAM_GROWTH \
  "$MK61_F401_WS0010_MAX_RAM_GROWTH" 0
require_equal MK61_F411_WS0010_MAX_RAM_GROWTH \
  "$MK61_F411_WS0010_MAX_RAM_GROWTH" 256
require_equal MK61_F401_WS0010_USB_MAX_RAM_GROWTH \
  "$MK61_F401_WS0010_USB_MAX_RAM_GROWTH" 0
require_equal MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH \
  "$MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH" 16
grep -Fq 'release_contract.py' "$budgets"
grep -Fq 'source "$root/tests/release_ram_budgets.sh"' "$ram_check"
require_equal check_release_ws0010_ram_call_count \
  "$(grep -Fc '"$root/tests/check_ws0010_ram.sh"' "$ram_check")" 4

# Local preflight and GitHub invoke the same repository-owned entry point.
grep -Fq 'run_f401_release_matrix.sh' "$preflight"
grep -Fq 'run_f401_release_matrix.sh' "$workflow"
grep -Fq 'run_f411_o3_compile_check.sh' "$preflight"
grep -Fq 'run_f411_o3_compile_check.sh' "$workflow"
grep -Fq 'run_stock_linker_compile_check.sh' "$preflight"
grep -Fq 'run_stock_linker_compile_check.sh' "$workflow"
if grep -Fq 'check_ws0010_ram.sh' "$preflight" ||
   grep -Fq 'check_ws0010_ram.sh' "$workflow"; then
  printf 'release entry points bypass the shared F401 matrix\n' >&2
  exit 1
fi

printf 'f411_release_policy_tests: ok\n'
