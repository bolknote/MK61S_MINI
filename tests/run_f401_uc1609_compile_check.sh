#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"
contract="$root/tools/release_contract.py"

fail() {
  printf 'F401 UC1609 compile check: %s\n' "$1" >&2
  exit 2
}

"$root/tests/run_f411_release_matrix.sh" --check-dependencies
command -v python3 >/dev/null 2>&1 ||
  fail 'python3 is required for the stack-usage release gate'

IFS=$'\t' read -r \
  case_id profile optimization board_flags _artifact flash_capacity \
  minimum_flash_headroom ram_capacity ram_limit stack_frame_limit \
  product _publish _usb_suspend _ws0010_graphics _features \
  <<<"$(python3 "$contract" cases --group f401-arduino --format tsv)"

temporary_root=0
if [[ -n "${MK61_F401_UC1609_BUILD_ROOT:-}" ]]; then
  build_root="$MK61_F401_UC1609_BUILD_ROOT"
  [[ ! -e "$build_root" ]] || fail "build root already exists: $build_root"
  mkdir -p "$build_root"
else
  build_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f401-uc1609.XXXXXX")"
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

# Size-LTO is part of the constrained production profile, not an optional
# experiment: it preserves the same alarm functionality as F411 while keeping
# the sealed-image safety reserve. Strict warnings and ELF gates still run on
# the exact linked artifact.
fqbn="STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=$optimization"
platform_ram_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'
strict_flags="$board_flags -DMK61_ENABLE_LOADABLE_MODULES=1 -DMK61_F401_PRODUCT_BUILD=$product -DMK61_REQUIRE_RESIDENT_CRC=1 -DMK61_REQUIRE_F401_SELECTIVE_O3=1 $platform_ram_flags -Werror -Wno-error=cpp"
layout_properties="$build_root/layout.properties"
"$arduino_cli" compile --fqbn "$fqbn" \
  --build-path "$build_root/properties-layout" \
  --show-properties=expanded "$sketch" > "$layout_properties"
variant_path="$(sed -n 's/^build\.variant\.path=//p' "$layout_properties" | tr -d '\r')"
ld_name="$(sed -n 's/^build\.ldscript=//p' "$layout_properties" | tr -d '\r')"
[[ -n "$variant_path" && -n "$ld_name" && -f "$variant_path/$ld_name" ]] ||
  fail 'cannot resolve the STM32F401 linker script'
portable_linker="$build_root/mk61-portable.ld"
python3 "$root/tools/.mk61-gcc/portable-layout.py" \
  "$variant_path/$ld_name" "$portable_linker"
resident_link_flags="-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected -Wl,--default-script=$portable_linker"

set +e
"$arduino_cli" compile \
  --warnings all \
  --fqbn "$fqbn" \
  --build-path "$compile_path" \
  --build-property "compiler.cpp.extra_flags=$strict_flags" \
  --build-property "compiler.c.extra_flags=$platform_ram_flags" \
  --build-property "compiler.c.elf.extra_flags=$resident_link_flags" \
  "$sketch" 2>&1 | tee "$compile_log"
pipeline_status=("${PIPESTATUS[@]}")
compile_status=${pipeline_status[0]}
tee_status=${pipeline_status[1]}
set -e

[[ "$compile_status" -eq 0 ]] ||
  fail "compile failed (status $compile_status)"
[[ "$tee_status" -eq 0 ]] || fail 'could not record compiler output'

unexpected_warnings="$(
  grep -F 'warning:' "$compile_log" |
    grep -Ev 'STM32RTC\.cpp:[0-9]+:[0-9]+: warning: #warning "only BCD mode is supported"|^lto-wrapper: warning: using serial compilation of [0-9]+ LTRANS jobs$' ||
    true
)"
if [[ -n "$unexpected_warnings" ]]; then
  printf 'Unexpected compiler warnings for F401 Classic V3 UC1609:\n%s\n' \
    "$unexpected_warnings" >&2
  exit 1
fi
python3 "$root/tests/analyze_stack_usage.py" \
  --compile-commands "$compile_path/compile_commands.json" \
  --source-root "$compile_path/sketch" --top 3 \
  --max-frame "$stack_frame_limit" \
  --summary-json "$compile_path/stack-usage.json"

# Arduino's generic low-memory warning starts below our deliberately chosen
# 80% regression boundary.  Enforce the numeric value so the check remains
# useful instead of either ignoring RAM entirely or depending on that message.
ram_line="$(grep -E 'Global variables use [0-9]+ bytes' "$compile_log" | tail -1 || true)"
[[ -n "$ram_line" ]] || fail 'could not read global RAM usage from compiler output'
ram_used="$(printf '%s\n' "$ram_line" | sed -E 's/.*Global variables use ([0-9]+) bytes.*/\1/')"
[[ "$ram_used" =~ ^[0-9]+$ ]] || fail "invalid global RAM usage: $ram_used"
if ((ram_used > ram_limit)); then
  fail "static RAM budget exceeded: $ram_used > $ram_limit bytes"
fi
printf 'F401 RAM budget: %d/%d bytes\n' "$ram_used" "$ram_limit"

test -s "$compile_path/mk61s-M.ino.elf" || fail 'missing ELF'
test -s "$compile_path/mk61s-M.ino.bin" || fail 'missing BIN'
"$root/tools/seal-firmware.sh" seal --max-size "$flash_capacity" \
  "$compile_path/mk61s-M.ino.bin"
"$root/tools/seal-firmware.sh" check --max-size "$flash_capacity" \
  "$compile_path/mk61s-M.ino.bin"

# Merely fitting below 256 KiB is not a release criterion: sealing appends a
# footer and future linker fluctuations must not break the public build. Use
# the explicit 7-KiB UC1609 floor from the release contract; character-display
# F401 products keep their independent 8-KiB floor.
sealed_size="$(wc -c < "$compile_path/mk61s-M.ino.bin" | tr -d '[:space:]')"
[[ "$sealed_size" =~ ^[0-9]+$ ]] || fail "invalid sealed BIN size: $sealed_size"
flash_headroom=$((flash_capacity - sealed_size))
if ((flash_headroom < minimum_flash_headroom)); then
  fail "sealed Flash headroom too small: $flash_headroom < $minimum_flash_headroom bytes"
fi
printf 'F401 sealed Flash budget: %d/%d bytes (%d bytes free)\n' \
  "$sealed_size" "$flash_capacity" "$flash_headroom"
python3 "$contract" resource-report \
  --case "$case_id" \
  --elf "$compile_path/mk61s-M.ino.elf" \
  --bin "$compile_path/mk61s-M.ino.bin" \
  --compile-commands "$compile_path/compile_commands.json" \
  --stack-summary "$compile_path/stack-usage.json" \
  --output-prefix "$compile_path/resource-report"

# This constrained production profile deliberately omits laboratory-only
# benchmarks and profilers; they remain available in qualification builds.
if grep -aFq 'Usage: bench' "$compile_path/mk61s-M.ino.elf"; then
  fail 'read benchmark unexpectedly present in constrained F401 image'
fi
if grep -aFq 'ANALOG us/n=' "$compile_path/mk61s-M.ino.elf"; then
  fail 'raw analog terminal report unexpectedly present in constrained F401 image'
fi
if grep -aFq 'PROF saved ' "$compile_path/mk61s-M.ino.elf"; then
  fail 'profile file exporter unexpectedly present in constrained F401 image'
fi
if grep -aFq 'PROF state=' "$compile_path/mk61s-M.ino.elf"; then
  fail 'live profiler unexpectedly present in constrained F401 image'
fi
if ! grep -aFq 'RTC ALARM' "$compile_path/mk61s-M.ino.elf"; then
  fail 'RTC alarm command unexpectedly missing from constrained F401 image'
fi
"$root/tests/check_global_constructors.sh" \
  "$compile_path/mk61s-M.ino.elf"
"$root/tests/check_early_dfu_elf.sh" \
  "$compile_path/mk61s-M.ino.elf"
"$root/tests/check_power_monitor_elf.sh" \
  "$compile_path/mk61s-M.ino.elf"
"$root/tests/check_rtc_alarm_elf.sh" \
  "$compile_path/mk61s-M.ino.elf"
"$root/tests/check_usb_suspend_elf.sh" --disabled \
  "$compile_path/mk61s-M.ino.elf"
"$root/tests/check_core_native_hot_paths_elf.sh" \
  "$compile_path/mk61s-M.ino.elf"

printf '\nF401 Classic V3 UC1609 Arduino compile check: OK\n'
