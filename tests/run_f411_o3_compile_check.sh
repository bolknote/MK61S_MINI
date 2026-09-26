#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"

fail() {
  printf 'F411 O3 compile check: %s\n' "$1" >&2
  exit 2
}

"$root/tests/run_f411_release_matrix.sh" --check-dependencies
command -v python3 >/dev/null 2>&1 || fail 'python3 is required'

temporary_root=0
if [[ -n "${MK61_F411_O3_BUILD_ROOT:-}" ]]; then
  build_root="$MK61_F411_O3_BUILD_ROOT"
  [[ ! -e "$build_root" ]] || fail "build root already exists: $build_root"
  mkdir -p "$build_root"
else
  build_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f411-o3.XXXXXX")"
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

# Classic V3 is the largest normal UC1609 product.  If its standard -O3 build
# retains a useful reserve, Mini and -O2 are covered with still more margin.
fqbn='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=o3std'
platform_ram_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'
strict_flags='-DMK61_BOARD_CLASSIC_V3 -DMK61_REQUIRE_RESIDENT_CRC=1 -DMK61_REQUIRE_MIXED_OPTIMIZATION=1 -Werror -Wno-error=cpp'
layout_properties="$build_root/layout.properties"
"$arduino_cli" compile --fqbn "$fqbn" \
  --build-path "$build_root/properties-layout" \
  --show-properties=expanded "$sketch" > "$layout_properties"
variant_path="$(sed -n 's/^build\.variant\.path=//p' "$layout_properties" | tr -d '\r')"
ld_name="$(sed -n 's/^build\.ldscript=//p' "$layout_properties" | tr -d '\r')"
[[ -n "$variant_path" && -n "$ld_name" && -f "$variant_path/$ld_name" ]] ||
  fail 'cannot resolve the STM32F411 linker script'
portable_linker="$build_root/mk61-portable.ld"
python3 "$root/tools/.mk61-gcc/portable-layout.py" \
  "$variant_path/$ld_name" "$portable_linker"
resident_link_flags="-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected -Wl,--default-script=$portable_linker"

set +e
"$arduino_cli" compile \
  --warnings all \
  --fqbn "$fqbn" \
  --build-path "$compile_path" \
  --build-property "compiler.cpp.extra_flags=$strict_flags $platform_ram_flags" \
  --build-property "compiler.c.extra_flags=$platform_ram_flags" \
  --build-property "compiler.c.elf.extra_flags=$resident_link_flags" \
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
  printf 'Unexpected compiler warnings for F411 Classic V3 O3:\n%s\n' \
    "$unexpected_warnings" >&2
  exit 1
fi

python3 "$root/tests/analyze_stack_usage.py" \
  --compile-commands "$compile_path/compile_commands.json" \
  --source-root "$compile_path/sketch" --top 3 \
  --max-frame 5120 \
  --summary-json "$compile_path/stack-usage.json"

test -s "$compile_path/mk61s-M.ino.bin" || fail 'missing BIN'
test -s "$compile_path/mk61s-M.ino.elf" || fail 'missing ELF'
python3 "$root/tests/check_app_memory_elf.py" \
  "$compile_path/mk61s-M.ino.elf"
"$root/tests/check_core_native_hot_paths_elf.sh" \
  "$compile_path/mk61s-M.ino.elf"
"$root/tests/check_no_resident_fmk_decoder_elf.sh" --allow-fmk \
  --allow-usbdisk \
  "$compile_path/mk61s-M.ino.elf"
"$root/tools/seal-firmware.sh" seal --max-size 524288 \
  "$compile_path/mk61s-M.ino.bin"
"$root/tools/seal-firmware.sh" check --max-size 524288 \
  "$compile_path/mk61s-M.ino.bin"

sealed_size="$(wc -c < "$compile_path/mk61s-M.ino.bin" | tr -d '[:space:]')"
[[ "$sealed_size" =~ ^[0-9]+$ ]] || fail "invalid sealed size: $sealed_size"
headroom=$((524288 - sealed_size))
# F411 now keeps the optional product modules resident by default.  Preserve a
# meaningful reserve for the largest manual -O3 profile without measuring it
# against the obsolete APP-by-default layout.
minimum_headroom=49152
if ((headroom < minimum_headroom)); then
  fail "sealed Flash headroom too small: $headroom < $minimum_headroom bytes"
fi

printf 'F411 Classic V3 O3 compatibility: %d/524288 bytes (%d bytes free)\n' \
  "$sealed_size" "$headroom"
printf 'F411 O3 compile check: OK\n'
