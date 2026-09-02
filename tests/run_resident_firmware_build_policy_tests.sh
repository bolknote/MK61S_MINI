#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

fail() {
  printf 'resident firmware build policy: %s\n' "$1" >&2
  exit 1
}

require_text() {
  local file=$1 text=$2
  grep -Fq -- "$text" "$file" ||
    fail "$file is missing: $text"
}

require_order() {
  local file=$1 first=$2 second=$3 first_line second_line
  first_line=$(grep -Fn -- "$first" "$file" | head -n 1 | cut -d: -f1 || true)
  second_line=$(grep -Fn -- "$second" "$file" | head -n 1 | cut -d: -f1 || true)
  [ -n "$first_line" ] && [ -n "$second_line" ] &&
    [ "$first_line" -lt "$second_line" ] ||
    fail "$file must apply '$first' before '$second'"
}

f411_matrix="$root/tests/run_f411_release_matrix.sh"
f401_check="$root/tests/run_f401_uc1609_compile_check.sh"
f401_bundle="$root/tools/build_f401_bundle.sh"
firmware_sh="$root/tools/.mk61-firmware/mk61-firmware.sh"
firmware_ps="$root/tools/.mk61-firmware/mk61-firmware.ps1"
gcc_cmake="$root/tools/.mk61-gcc/CMakeLists.txt"
gcc_ps="$root/tools/.mk61-gcc/build.ps1"
board="$root/tools/.mk61-arduino-board/hardware/mk61/stm32/boards.txt"
board_hook_sh="$root/tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-app-postbuild.sh"
board_hook_ps="$root/tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-app-postbuild.ps1"
board_install_sh="$root/tools/.mk61-arduino-board/install.sh"
board_install_ps="$root/tools/.mk61-arduino-board/install.ps1"

for file in "$f411_matrix" "$f401_check" "$f401_bundle" \
    "$firmware_sh" "$firmware_ps" "$gcc_cmake" "$gcc_ps" "$board" \
    "$board_hook_sh" "$board_hook_ps" "$board_install_sh" \
    "$board_install_ps"; do
  test -s "$file" || fail "missing build path: $file"
done

require_text "$f411_matrix" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$f411_matrix" 'seal-firmware.sh" seal --max-size 524288'
require_text "$f411_matrix" 'seal-firmware.sh" check --max-size 524288'
require_text "$f411_matrix" 'analyze_stack_usage.py'
require_text "$f401_check" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$f401_check" 'seal-firmware.sh" seal --max-size 262144'
require_text "$f401_check" 'usb=CDCgen,opt=oslto'
require_text "$f401_check" 'check_rtc_alarm_elf.sh'
require_text "$f401_check" 'analyze_stack_usage.py'
require_text "$f411_matrix" 'check_rtc_alarm_elf.sh'

require_text "$f401_bundle" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$f401_bundle" 'seal-firmware.sh" seal --max-size 262144'
require_text "$f401_bundle" 'analyze_stack_usage.py'
require_text "$f401_bundle" '-flto -fipa-pta'
require_text "$f401_bundle" 'opt=oslto'
require_text "$f401_bundle" '--export-dynamic-symbol-list='
require_text "$f401_bundle" 'system-app-exports.list'
require_order "$f401_bundle" 'seal-firmware.sh" seal' 'build_module focal'

require_text "$firmware_sh" "RESIDENT_RELEASE_FLAGS='-DMK61_REQUIRE_RESIDENT_CRC=1'"
require_text "$firmware_sh" 'seal-firmware.sh" seal --max-size 524288'
require_text "$firmware_ps" "ResidentReleaseFlags = '-DMK61_REQUIRE_RESIDENT_CRC=1'"
require_text "$firmware_ps" "'tools/seal-firmware.ps1'"
require_text "$firmware_ps" "'-InputFile', \$sourceArtifact, '-MaxSize', '524288'"

require_text "$gcc_cmake" 'MK61_REQUIRE_RESIDENT_CRC=${MK61_REQUIRE_RESIDENT_CRC}'
require_text "$gcc_cmake" 'analyze_stack_usage.py'
require_text "$gcc_ps" "'-DMK61_REQUIRE_RESIDENT_CRC=1'"
require_text "$gcc_ps" "'tools/seal-firmware.ps1'"
require_order "$gcc_ps" "'seal'," "'System APP builder'"
require_text "$gcc_ps" "'--change-addresses', '0x08000000'"
require_text "$root/system_apps/.tool/build.ps1" 'check_stack_usage.py'
require_text "$root/system_apps/.tool/build.ps1" "'-fipa-pta'"

require_text "$board" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$board_hook_sh" 'seal_resident "$resident_bin"'
require_text "$board_hook_ps" "'seal-firmware.ps1'"
for installer in "$board_install_sh" "$board_install_ps"; do
  require_text "$installer" 'mk61_firmware_seal.cpp'
  require_text "$installer" 'resident_firmware_format.hpp'
  require_text "$installer" 'rust_types.h'
  require_text "$installer" 'seal-firmware.ps1'
done

printf 'resident_firmware_build_policy_tests: ok\n'
