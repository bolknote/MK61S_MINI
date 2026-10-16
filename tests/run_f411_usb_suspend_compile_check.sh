#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
contract="$root/tools/release_contract.py"

fail() {
  printf 'F411 USB suspend compile check: %s\n' "$1" >&2
  exit 2
}

"$root/tests/run_f411_release_matrix.sh" --check-dependencies

temporary_root=0
if [[ -n "${MK61_F411_USB_SUSPEND_BUILD_ROOT:-}" ]]; then
  build_root="$MK61_F411_USB_SUSPEND_BUILD_ROOT"
  [[ ! -e "$build_root" ]] || fail "build root already exists: $build_root"
  mkdir -p "$build_root"
else
  build_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f411-usb-suspend.XXXXXX")"
  temporary_root=1
fi

cleanup() {
  if [[ "$temporary_root" -eq 1 ]]; then
    rm -rf "$build_root"
  fi
}
trap cleanup EXIT HUP INT TERM

compile_profile() {
  local case_id="$1"
  local profile="$2"
  local board_flags="$3"
  local flash_capacity="$4"
  local minimum_flash_headroom="$5"
  local ram_capacity="$6"
  local ram_limit="$7"
  local stack_frame_limit="$8"
  local optimization="$9"
  local name="${case_id#f411-stop-}"
  local compile_path="$build_root/build-$name"
  local compile_log="$compile_path/compile.log"
  local stack_summary="$compile_path/stack-usage.json"
  mkdir -p "$compile_path"
  printf '\nNative F411 USB suspend production profile: %s\n' "$name"
  # No STOP override: production defaults select deep idle and USB preservation.
  python3 "$root/tools/.mk61-gcc/build-standalone.py" \
    --release-case "$case_id" --build-path "$compile_path" \
    --jobs "${MK61_BUILD_JOBS:-4}" 2>&1 | tee "$compile_log"
  cp "$compile_path/resident.elf" "$compile_path/mk61s-M.ino.elf"
  cp "$compile_path/resident.bin" "$compile_path/mk61s-M.ino.bin"
  local tool_bin
  tool_bin="$(python3 - "$compile_path/compile_commands.json" "$root/tools" <<'PYTOOLS'
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
from release_contract import discover_binutils
print(discover_binutils(Path(sys.argv[1]))[1].parent)
PYTOOLS
)"
  export PATH="$tool_bin:$PATH"
  python3 "$root/tests/check_standalone_sdk_build.py" "$compile_path/compile_commands.json"
  python3 "$root/tests/check_stm32_standalone_build.py" "$compile_path/compile_commands.json"
  python3 "$root/tests/check_native_runtime_libraries.py" "$compile_path/resident.map" --without-libc
  python3 "$root/tests/check_compiler_warnings.py" \
    --log "$compile_log" \
    --compile-commands "$compile_path/compile_commands.json"

  python3 "$root/tests/analyze_stack_usage.py" \
    --compile-commands "$compile_path/compile_commands.json" \
    --source-root "$root/code" --top 3 \
    --max-frame "$stack_frame_limit" --summary-json "$stack_summary"

  local elf="$compile_path/mk61s-M.ino.elf"
  local bin="$compile_path/mk61s-M.ino.bin"
  [[ -s "$elf" ]] || fail "$name ELF is missing"
  [[ -s "$bin" ]] || fail "$name BIN is missing"
  python3 "$root/tests/check_usb_cdc_rx_elf.py" "$elf" \
    --compile-commands "$compile_path/compile_commands.json"
  "$root/tools/seal-firmware.sh" seal --max-size "$flash_capacity" "$bin"
  "$root/tools/seal-firmware.sh" check --max-size "$flash_capacity" "$bin"
  python3 "$contract" resource-report \
    --case "$case_id" --elf "$elf" --bin "$bin" \
    --compile-commands "$compile_path/compile_commands.json" \
    --stack-summary "$stack_summary" \
    --output-prefix "$compile_path/resource-report"
  "$root/tests/check_global_constructors.sh" "$elf"
  python3 "$root/tests/check_app_memory_elf.py" "$elf"
  "$root/tests/check_early_dfu_elf.sh" "$elf"
  "$root/tests/check_power_monitor_elf.sh" "$elf"
  "$root/tests/check_rtc_alarm_elf.sh" "$elf"
  "$root/tests/check_usb_suspend_elf.sh" "$elf"
  "$root/tests/check_core_native_hot_paths_elf.sh" "$elf"
  "$root/tests/check_no_resident_fmk_decoder_elf.sh" --allow-fmk \
    --allow-usbdisk "$elf"
}

profile_count="$(python3 "$contract" cases --group f411-stop --format count)"
while IFS=$'\t' read -r \
    case_id profile optimization board_flags _artifact flash_capacity \
    minimum_flash_headroom ram_capacity ram_limit stack_frame_limit \
    _product _publish _usb_suspend _ws0010_graphics _focal _basic _wbmp \
    _markdown _chip8 _usb_screen _graphics _extended_font _user_explorer \
    _math_backend _lto; do
  compile_profile "$case_id" "$profile" "$board_flags" "$flash_capacity" \
    "$minimum_flash_headroom" "$ram_capacity" "$ram_limit" \
    "$stack_frame_limit" "$optimization"
done < <(python3 "$contract" cases --group f411-stop --format tsv)

printf '\nF411 USB suspend production compile check: OK (%d profiles)\n' \
  "$profile_count"
