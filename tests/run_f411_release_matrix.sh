#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"
expected_cli_version=1.5.1
expected_core_version=2.12.0

fail() {
  printf 'F411 release matrix: %s\n' "$1" >&2
  exit 2
}

command -v "$arduino_cli" >/dev/null 2>&1 ||
  fail "arduino-cli is not installed: $arduino_cli"

cli_version="$("$arduino_cli" version 2>/dev/null || true)"
printf '%s\n' "$cli_version" |
  grep -Eq "Version:[[:space:]]+$expected_cli_version([[:space:]]|$)" ||
  fail "arduino-cli $expected_cli_version is required"

"$arduino_cli" core list |
  grep -Eq "^STMicroelectronics:stm32[[:space:]]+$expected_core_version([[:space:]]|$)" ||
  fail "STM32 Core $expected_core_version is required"
"$arduino_cli" lib list |
  grep -Eq '^LiquidCrystal[[:space:]]+1\.0\.7([[:space:]]|$)' ||
  fail 'LiquidCrystal 1.0.7 is required'
"$arduino_cli" lib list |
  grep -Eq '^STM32duino RTC[[:space:]]+1\.9\.0([[:space:]]|$)' ||
  fail 'STM32duino RTC 1.9.0 is required'

if [[ "${1:-}" == "--check-dependencies" ]]; then
  printf 'F411 release dependencies: OK\n'
  exit 0
fi
if [[ $# -ne 0 ]]; then
  fail "unknown argument: $1"
fi

temporary_root=0
if [[ -n "${MK61_F411_BUILD_ROOT:-}" ]]; then
  matrix_root="$MK61_F411_BUILD_ROOT"
  if [[ -e "$matrix_root" ]]; then
    fail "build root already exists: $matrix_root"
  fi
  mkdir -p "$matrix_root"
else
  matrix_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f411-release.XXXXXX")"
  temporary_root=1
fi

cleanup() {
  if [[ "$temporary_root" -eq 1 ]]; then
    rm -rf "$matrix_root"
  fi
}
trap cleanup EXIT HUP INT TERM

sketch="$matrix_root/mk61s-M"
mkdir -p "$sketch"
cp -R "$root/code/." "$sketch/"

output_dir="${MK61_FIRMWARE_OUTPUT_DIR:-}"
firmware_tag="${MK61_FIRMWARE_TAG:-local}"
if [[ -n "$output_dir" ]]; then
  [[ "$firmware_tag" =~ ^[A-Za-z0-9._-]+$ ]] ||
    fail "invalid firmware tag: $firmware_tag"
  mkdir -p "$output_dir"
fi

fqbn='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=osstd'
fqbn_lto='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=o3lto'
strict_flags='-Werror -Wno-error=cpp'
platform_ram_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'
variant_index=0
variant_count=14

compile_variant() {
  local name="$1"
  local variant_fqbn="$2"
  local board_flags="$3"
  local artifact_name="$4"
  local build_path="$matrix_root/build-$name"
  local compile_log="$build_path/compile.log"
  local compile_flags="$board_flags $platform_ram_flags $strict_flags"
  variant_index=$((variant_index + 1))
  printf '\n[%d/%d] F411 %s\n' "$variant_index" "$variant_count" "$name"
  mkdir -p "$build_path"
  set +e
  "$arduino_cli" compile \
    --warnings all \
    --fqbn "$variant_fqbn" \
    --build-path "$build_path" \
    --build-property "compiler.cpp.extra_flags=$compile_flags" \
    --build-property "compiler.c.extra_flags=$platform_ram_flags" \
    "$sketch" 2>&1 | tee "$compile_log"
  local pipeline_status=("${PIPESTATUS[@]}")
  local compile_status=${pipeline_status[0]}
  local tee_status=${pipeline_status[1]}
  set -e
  [[ "$compile_status" -eq 0 ]] ||
    fail "compile failed for $name (status $compile_status)"
  [[ "$tee_status" -eq 0 ]] ||
    fail "could not record compiler output for $name"
  local unexpected_warnings
  unexpected_warnings="$(
    grep -F 'warning:' "$compile_log" |
      grep -Ev 'STM32RTC\.cpp:[0-9]+:[0-9]+: warning: #warning "only BCD mode is supported"|^lto-wrapper: warning: using serial compilation of [0-9]+ LTRANS jobs$' ||
      true
  )"
  if [[ -n "$unexpected_warnings" ]]; then
    printf 'Unexpected compiler warnings for %s:\n%s\n' \
      "$name" "$unexpected_warnings" >&2
    exit 1
  fi
  test -s "$build_path/mk61s-M.ino.elf" ||
    fail "missing ELF for $name"
  test -s "$build_path/mk61s-M.ino.bin" ||
    fail "missing BIN for $name"
  "$root/tests/check_global_constructors.sh" \
    "$build_path/mk61s-M.ino.elf"
  "$root/tests/check_early_dfu_elf.sh" \
    "$build_path/mk61s-M.ino.elf"
  if [[ -n "$output_dir" && -n "$artifact_name" ]]; then
    cp "$build_path/mk61s-M.ino.bin" \
      "$output_dir/${artifact_name}-${firmware_tag}.bin"
  fi
}

compile_variant lcd1602-a00 "$fqbn" \
  '-DMK61_LCD1602_A00' 'mk61s-M-lcd1602-a00-f411'
compile_variant lcd1602-a00-usb-screen "$fqbn" \
  '-DMK61_LCD1602_A00 -DMK61_ENABLE_USB_SCREEN=1' ''
compile_variant lcd1602-a00-lto "$fqbn_lto" \
  '-DMK61_LCD1602_A00' ''
compile_variant lcd1602-a02 "$fqbn" \
  '-DMK61_LCD1602_A02' 'mk61s-M-lcd1602-a02-f411'
compile_variant oled1602-ws0010 "$fqbn" \
  '-DMK61_OLED1602_WS0010' 'mk61s-M-mini-v3-oled1602-ws0010-f411'
compile_variant oled1602-ws0010-usb-screen "$fqbn" \
  '-DMK61_OLED1602_WS0010 -DMK61_ENABLE_USB_SCREEN=1' ''
compile_variant oled1602-ws0010-graphics "$fqbn" \
  '-DMK61_OLED1602_WS0010 -DMK61_WS0010_GRAPHICS_100X16=1' ''
compile_variant oled1602-ws0010-usb-screen-graphics "$fqbn" \
  '-DMK61_OLED1602_WS0010 -DMK61_ENABLE_USB_SCREEN=1 -DMK61_WS0010_GRAPHICS_100X16=1' ''
compile_variant mini-v2-lcd1602-a00 "$fqbn" \
  '-DREVISION_V2 -DMK61_LCD1602_A00' \
  'mk61s-M-mini-v2-lcd1602-a00-f411'
compile_variant mini-v2-lcd1602-a02 "$fqbn" \
  '-DREVISION_V2 -DMK61_LCD1602_A02' \
  'mk61s-M-mini-v2-lcd1602-a02-f411'
compile_variant classic-v2 "$fqbn" \
  '-DMK61_BOARD_CLASSIC_V2' 'mk61s-M-classic-v2-uc1609-f411'
compile_variant classic-v3 "$fqbn" \
  '-DMK61_BOARD_CLASSIC_V3' 'mk61s-M-classic-v3-uc1609-f411'
compile_variant classic-v3-usb-screen "$fqbn" \
  '-DMK61_BOARD_CLASSIC_V3 -DMK61_ENABLE_USB_SCREEN=1' ''
compile_variant 40th "$fqbn" \
  '-DMK61_BOARD_40TH' 'mk61s-M-40th-f411'

printf '\nF411 strict release matrix: OK (%d variants)\n' "$variant_count"
