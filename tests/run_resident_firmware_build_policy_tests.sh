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
f411_o3_check="$root/tests/run_f411_o3_compile_check.sh"
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
release_workflow="$root/.github/workflows/firmware-release.yml"

for file in "$f411_matrix" "$f411_o3_check" "$f401_check" "$f401_bundle" \
    "$firmware_sh" "$firmware_ps" "$gcc_cmake" "$gcc_ps" "$board" \
    "$board_hook_sh" "$board_hook_ps" "$board_install_sh" \
    "$board_install_ps" "$release_workflow"; do
  test -s "$file" || fail "missing build path: $file"
done

require_text "$f411_matrix" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$f411_matrix" 'seal-firmware.sh" seal --max-size "$flash_capacity"'
require_text "$f411_matrix" 'seal-firmware.sh" check --max-size "$flash_capacity"'
require_text "$f411_matrix" 'cases --group f411-release --format tsv'
require_text "$f411_matrix" 'analyze_stack_usage.py'
require_text "$f411_o3_check" 'opt=o3std'
require_text "$f411_o3_check" 'MK61_REQUIRE_MIXED_OPTIMIZATION=1'
require_text "$f411_o3_check" 'analyze_stack_usage.py'
require_text "$f411_o3_check" 'minimum_headroom=65536'
require_text "$f401_check" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$f401_check" 'MK61_REQUIRE_F401_SELECTIVE_O3=1'
require_text "$f401_check" 'seal-firmware.sh" seal --max-size "$flash_capacity"'
require_text "$f401_check" 'usb=CDCgen,opt=$optimization'
require_text "$f401_check" 'cases --group f401-arduino --format tsv'
require_text "$f401_check" 'check_rtc_alarm_elf.sh'
require_text "$f401_check" 'check_no_resident_fmk_decoder_elf.sh'
require_text "$f401_check" 'analyze_stack_usage.py'
require_text "$f411_matrix" 'check_rtc_alarm_elf.sh'
require_text "$f411_matrix" 'check_no_resident_fmk_decoder_elf.sh'

require_text "$f401_bundle" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$f401_bundle" 'MK61_REQUIRE_F401_SELECTIVE_O3=1'
require_text "$f401_bundle" 'seal-firmware.sh" seal --max-size 262144'
require_text "$f401_bundle" 'analyze_stack_usage.py'
require_text "$f401_bundle" 'opt=oslto'
require_text "$f401_bundle" 'MK61_ENABLE_LOADABLE_MODULES=1'
require_text "$f401_bundle" 'portable-layout.py'
require_text "$f401_bundle" 'build_system_app_bundle.py'
if grep -Fq -- '--export-dynamic-symbol-list=' "$f401_bundle" ||
   grep -Fq -- 'system-app-exports.list' "$f401_bundle"; then
  fail 'F401 bundle still exposes resident C++ symbols to System APP'
fi
require_order "$f401_bundle" 'seal-firmware.sh" seal' 'build_system_app_bundle.py'

require_text "$firmware_sh" "RESIDENT_RELEASE_FLAGS='-DMK61_REQUIRE_RESIDENT_CRC=1'"
require_text "$firmware_sh" 'seal-firmware.sh" seal --max-size 524288'
require_text "$firmware_ps" "ResidentReleaseFlags = '-DMK61_REQUIRE_RESIDENT_CRC=1'"
require_text "$firmware_ps" "'tools/seal-firmware.ps1'"
require_text "$firmware_ps" "'-InputFile', \$sourceArtifact, '-MaxSize', '524288'"

require_text "$gcc_cmake" 'MK61_REQUIRE_RESIDENT_CRC=${MK61_REQUIRE_RESIDENT_CRC}'
require_text "$gcc_cmake" 'MK61_REQUIRE_F401_SELECTIVE_O3=1'
require_text "$gcc_cmake" 'analyze_stack_usage.py'
require_text "$gcc_ps" "'-DMK61_REQUIRE_RESIDENT_CRC=1'"
require_text "$gcc_ps" "'tools/seal-firmware.ps1'"
require_order "$gcc_ps" "'seal'," "'System APP builder'"
require_text "$gcc_ps" "'--change-addresses', '0x08000000'"
require_text "$root/system_apps/.tool/build.ps1" 'build_system_app_bundle.py'
require_text "$root/tools/build_system_app_bundle.py" 'build_portable_app.py'
require_text "$root/tools/build_portable_app.py" 'analyze_stack_usage.py'
require_text "$root/tools/build_portable_app.py" '"-fipa-pta"'

require_text "$board" 'MK61_REQUIRE_RESIDENT_CRC=1'
require_text "$board_hook_sh" 'seal_resident "$resident_bin"'
require_text "$board_hook_ps" "'seal-firmware.ps1'"
for installer in "$board_install_sh" "$board_install_ps"; do
  require_text "$installer" 'mk61_firmware_seal.cpp'
  require_text "$installer" 'resident_firmware_format.hpp'
  require_text "$installer" 'rust_types.h'
  require_text "$installer" 'seal-firmware.ps1'
done

arduino_ide_job="$(sed -n \
  '/^  arduino-ide-windows:/,/^  build-release:/p' "$release_workflow")"
for required in \
    'mk61_platform=mini_v2,mk61_display=lcd_a00' \
    'mk61_focal=enabled,mk61_basic=enabled,mk61_documents=markdown' \
    "'FOCAL.APP' = 1" \
    "'BASIC.APP' = 2" \
    "'MARKDOWN.APP' = 6" \
    "'SETUP.APP' = 7" \
    "'USBDISK.APP' = 8" \
    'System/HELP0.TXT' \
    'System/HELP1.TXT' \
    '-DREVISION_V2' \
    '-DMK61_ENABLE_FOCAL=1' \
    '-DMK61_ENABLE_TINYBASIC=1' \
    '-DMK61_ENABLE_MARKDOWN_VIEWER=1'; do
  printf '%s\n' "$arduino_ide_job" | grep -Fq -- "$required" ||
    fail "Windows Arduino IDE V2 job is missing: $required"
done
if printf '%s\n' "$arduino_ide_job" |
    grep -Fq -- 'mk61_documents=disabled'; then
  fail 'Windows Arduino IDE V2 job disables the document APP'
fi

printf 'resident_firmware_build_policy_tests: ok\n'
