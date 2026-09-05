#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"
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

sketch="$build_root/mk61s-M"
mkdir -p "$sketch"
cp -R "$root/code/." "$sketch/"

fqbn='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=osstd'
platform_ram_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'
wrap_flags='-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected'

compile_profile() {
  local case_id="$1"
  local profile="$2"
  local board_flags="$3"
  local flash_capacity="$4"
  local minimum_flash_headroom="$5"
  local ram_capacity="$6"
  local ram_limit="$7"
  local stack_frame_limit="$8"
  local name="${case_id#f411-stop-}"
  local compile_path="$build_root/build-$name"
  local compile_log="$compile_path/compile.log"
  local stack_summary="$compile_path/stack-usage.json"
  local strict_flags="$board_flags -DMK61_REQUIRE_RESIDENT_CRC=1 $platform_ram_flags -Werror -Wno-error=cpp"
  mkdir -p "$compile_path"

  printf '\nF411 USB suspend production profile: %s\n' "$name"
  # Deliberately pass no STOP feature override: both builds must obtain deep
  # idle, USB preservation and automatic re-entry from production defaults.
  set +e
  "$arduino_cli" compile \
    --warnings all \
    --fqbn "$fqbn" \
    --build-path "$compile_path" \
    --build-property "compiler.cpp.extra_flags=$strict_flags" \
    --build-property "compiler.c.extra_flags=$platform_ram_flags" \
    --build-property "compiler.c.elf.extra_flags=$wrap_flags" \
    "$sketch" 2>&1 | tee "$compile_log"
  local pipeline_status=("${PIPESTATUS[@]}")
  local compile_status=${pipeline_status[0]}
  local tee_status=${pipeline_status[1]}
  set -e

  [[ "$compile_status" -eq 0 ]] ||
    fail "$name compile failed (status $compile_status)"
  [[ "$tee_status" -eq 0 ]] || fail "$name compile log could not be recorded"

  local unexpected_warnings
  unexpected_warnings="$(
    grep -F 'warning:' "$compile_log" |
      grep -Ev 'STM32RTC\.cpp:[0-9]+:[0-9]+: warning: #warning "only BCD mode is supported"' ||
      true
  )"
  if [[ -n "$unexpected_warnings" ]]; then
    printf 'Unexpected compiler warnings for F411 USB suspend %s:\n%s\n' \
      "$name" "$unexpected_warnings" >&2
    exit 1
  fi

  python3 "$root/tests/analyze_stack_usage.py" \
    --compile-commands "$compile_path/compile_commands.json" \
    --source-root "$compile_path/sketch" --top 3 \
    --max-frame "$stack_frame_limit" --summary-json "$stack_summary"

  local flash_line ram_line flash_used flash_max ram_used ram_max
  flash_line="$(grep -E '^Sketch uses [0-9]+ bytes .*Maximum is [0-9]+ bytes\.$' \
    "$compile_log" | tail -n 1)"
  ram_line="$(grep -E '^Global variables use [0-9]+ bytes .*Maximum is [0-9]+ bytes\.$' \
    "$compile_log" | tail -n 1)"
  [[ -n "$flash_line" ]] || fail "$name Flash usage is missing"
  [[ -n "$ram_line" ]] || fail "$name global RAM usage is missing"
  flash_used="$(sed -E 's/^Sketch uses ([0-9]+) bytes .*$/\1/' <<<"$flash_line")"
  flash_max="$(sed -E 's/^.*Maximum is ([0-9]+) bytes\.$/\1/' <<<"$flash_line")"
  ram_used="$(sed -E 's/^Global variables use ([0-9]+) bytes .*$/\1/' <<<"$ram_line")"
  ram_max="$(sed -E 's/^.*Maximum is ([0-9]+) bytes\.$/\1/' <<<"$ram_line")"
  ((flash_max == flash_capacity)) ||
    fail "$name Flash capacity differs from contract: $flash_max != $flash_capacity"
  ((ram_max == ram_capacity)) ||
    fail "$name RAM capacity differs from contract: $ram_max != $ram_capacity"
  ((ram_used <= ram_limit)) ||
    fail "$name static RAM exceeds $ram_limit bytes: $ram_used"
  printf 'F411 USB suspend %s budgets: Flash %d/%d, RAM %d/%d bytes\n' \
    "$name" "$flash_used" "$flash_max" "$ram_used" "$ram_max"

  local elf="$compile_path/mk61s-M.ino.elf"
  local bin="$compile_path/mk61s-M.ino.bin"
  [[ -s "$elf" ]] || fail "$name ELF is missing"
  [[ -s "$bin" ]] || fail "$name BIN is missing"
  "$root/tools/seal-firmware.sh" seal --max-size "$flash_capacity" "$bin"
  "$root/tools/seal-firmware.sh" check --max-size "$flash_capacity" "$bin"
  python3 "$contract" resource-report \
    --case "$case_id" --elf "$elf" --bin "$bin" \
    --compile-commands "$compile_path/compile_commands.json" \
    --stack-summary "$stack_summary" \
    --output-prefix "$compile_path/resource-report"
  "$root/tests/check_global_constructors.sh" "$elf"
  "$root/tests/check_early_dfu_elf.sh" "$elf"
  "$root/tests/check_power_monitor_elf.sh" "$elf"
  "$root/tests/check_rtc_alarm_elf.sh" "$elf"
  "$root/tests/check_usb_suspend_elf.sh" "$elf"
}

profile_count="$(python3 "$contract" cases --group f411-stop --format count)"
while IFS=$'\t' read -r \
    case_id profile _optimization board_flags _artifact flash_capacity \
    minimum_flash_headroom ram_capacity ram_limit stack_frame_limit \
    _product _publish _usb_suspend _ws0010_graphics _focal _basic _wbmp \
    _markdown _chip8 _usb_screen _graphics _extended_font _user_explorer \
    _math_backend _lto; do
  compile_profile "$case_id" "$profile" "$board_flags" "$flash_capacity" \
    "$minimum_flash_headroom" "$ram_capacity" "$ram_limit" \
    "$stack_frame_limit"
done < <(python3 "$contract" cases --group f411-stop --format tsv)

printf '\nF411 USB suspend production compile check: OK (%d profiles)\n' \
  "$profile_count"
