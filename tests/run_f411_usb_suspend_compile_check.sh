#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"

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
compile_path="$build_root/build"
compile_log="$build_root/compile.log"
mkdir -p "$sketch" "$compile_path"
cp -R "$root/code/." "$sketch/"

fqbn='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=osstd'
platform_ram_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'
# Deliberately pass no STOP feature override here: this compiles the same
# production defaults shipped by the ordinary F411 mini V3 WS0010 release.
strict_flags="-DMK61_OLED1602_WS0010 -DMK61_REQUIRE_RESIDENT_CRC=1 $platform_ram_flags -Werror -Wno-error=cpp"
wrap_flags='-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected'

set +e
"$arduino_cli" compile \
  --warnings all \
  --fqbn "$fqbn" \
  --build-path "$compile_path" \
  --build-property "compiler.cpp.extra_flags=$strict_flags" \
  --build-property "compiler.c.extra_flags=$platform_ram_flags" \
  --build-property "compiler.c.elf.extra_flags=$wrap_flags" \
  "$sketch" 2>&1 | tee "$compile_log"
pipeline_status=("${PIPESTATUS[@]}")
compile_status=${pipeline_status[0]}
tee_status=${pipeline_status[1]}
set -e

[[ "$compile_status" -eq 0 ]] || fail "compile failed (status $compile_status)"
[[ "$tee_status" -eq 0 ]] || fail 'could not record compiler output'

unexpected_warnings="$(
  grep -F 'warning:' "$compile_log" |
    grep -Ev 'STM32RTC\.cpp:[0-9]+:[0-9]+: warning: #warning "only BCD mode is supported"' ||
    true
)"
if [[ -n "$unexpected_warnings" ]]; then
  printf 'Unexpected compiler warnings for F411 USB suspend production:\n%s\n' \
    "$unexpected_warnings" >&2
  exit 1
fi

flash_line="$(grep -E '^Sketch uses [0-9]+ bytes .*Maximum is [0-9]+ bytes\.$' \
  "$compile_log" | tail -n 1)"
ram_line="$(grep -E '^Global variables use [0-9]+ bytes .*Maximum is [0-9]+ bytes\.$' \
  "$compile_log" | tail -n 1)"
[[ -n "$flash_line" ]] || fail 'could not read Flash usage'
[[ -n "$ram_line" ]] || fail 'could not read global RAM usage'
flash_used="$(sed -E 's/^Sketch uses ([0-9]+) bytes .*$/\1/' <<<"$flash_line")"
flash_max="$(sed -E 's/^.*Maximum is ([0-9]+) bytes\.$/\1/' <<<"$flash_line")"
ram_used="$(sed -E 's/^Global variables use ([0-9]+) bytes .*$/\1/' <<<"$ram_line")"
ram_max="$(sed -E 's/^.*Maximum is ([0-9]+) bytes\.$/\1/' <<<"$ram_line")"
((flash_max - flash_used >= 131072)) ||
  fail "production Flash headroom is below 128 KiB: $((flash_max - flash_used))"
((ram_used <= 32768)) ||
  fail "production static RAM exceeds 32 KiB: $ram_used"
printf 'F411 USB suspend budgets: Flash %d/%d, RAM %d/%d bytes\n' \
  "$flash_used" "$flash_max" "$ram_used" "$ram_max"

elf="$compile_path/mk61s-M.ino.elf"
bin="$compile_path/mk61s-M.ino.bin"
[[ -s "$elf" ]] || fail 'missing ELF'
[[ -s "$bin" ]] || fail 'missing BIN'
"$root/tools/seal-firmware.sh" seal --max-size 524288 "$bin"
"$root/tools/seal-firmware.sh" check --max-size 524288 "$bin"
"$root/tests/check_global_constructors.sh" "$elf"
"$root/tests/check_early_dfu_elf.sh" "$elf"
"$root/tests/check_power_monitor_elf.sh" "$elf"
"$root/tests/check_rtc_alarm_elf.sh" "$elf"
"$root/tests/check_usb_suspend_elf.sh" "$elf"

printf '\nF411 USB suspend production compile check: OK\n'
