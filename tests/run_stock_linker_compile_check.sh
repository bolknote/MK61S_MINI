#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"

fail() {
  printf 'Stock-linker compile check: %s\n' "$1" >&2
  exit 2
}

"$root/tests/run_f411_release_matrix.sh" --check-dependencies

temporary_root=0
if [[ -n "${MK61_STOCK_LINKER_BUILD_ROOT:-}" ]]; then
  build_root="$MK61_STOCK_LINKER_BUILD_ROOT"
  [[ ! -e "$build_root" ]] || fail "build root already exists: $build_root"
  mkdir -p "$build_root"
else
  build_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-stock-linker.XXXXXX")"
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

# Deliberately omit compiler.c.elf.extra_flags and therefore
# mk61-portable.ld.  This is the direct Generic STM32F4 Arduino IDE path that
# exposed strong undefined __mk61_dynamic_begin/end references under LTO.
common_flags='-DMK61_BOARD_CLASSIC_V2 -DMK61_ENABLE_FOCAL=1 -DMK61_ENABLE_TINYBASIC=1 -DMK61_ENABLE_WBMP_VIEWER=1 -DMK61_ENABLE_MARKDOWN_VIEWER=1 -DMK61_ENABLE_CHIP8=1 -DMK61_ENABLE_LOADABLE_MODULES=1 -DMK61_ENABLE_EXTENDED_FONT_SETTINGS=1 -DMK61_USER_EXPLORER_SHORTCUT=1 -DMK61_MATH_BACKEND=1 -Werror -Wno-error=cpp'
platform_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'

compile_case() {
  local label=$1 part=$2 maximum_size=$3 minimum_headroom=$4
  local path="$build_root/$label" log="$build_root/$label.log"
  local fqbn="STMicroelectronics:stm32:GenF4:pnum=$part,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=oslto"
  local case_flags="$common_flags -DMK61_ENABLE_USB_SCREEN=1"
  # The F401 public Classic/UC1609 profile uses its physical display and does
  # not also carry the optional USB Screen framebuffer. The latter is still
  # exercised by F411 below. Keeping it here tested an artificial all-features
  # combination and eventually overflowed the 256-KiB stock linker layout.
  if [[ "$label" == F401 ]]; then
    case_flags="$common_flags -DMK61_ENABLE_USB_SCREEN=0 -DMK61_F401_PRODUCT_BUILD=1"
  fi
  mkdir -p "$path"
  set +e
  "$arduino_cli" compile \
    --warnings all \
    --fqbn "$fqbn" \
    --build-path "$path" \
    --build-property "compiler.cpp.extra_flags=$case_flags $platform_flags" \
    --build-property "compiler.c.extra_flags=$platform_flags" \
    "$sketch" 2>&1 | tee "$log"
  local pipeline_status=("${PIPESTATUS[@]}")
  local compile_status=${pipeline_status[0]}
  local tee_status=${pipeline_status[1]}
  set -e
  [[ "$compile_status" -eq 0 ]] ||
    fail "$label compile failed (status $compile_status)"
  [[ "$tee_status" -eq 0 ]] || fail "could not record $label output"
  test -s "$path/mk61s-M.ino.bin" || fail "$label BIN is missing"
  test -s "$path/mk61s-M.ino.elf" || fail "$label ELF is missing"
  local size
  size="$(wc -c < "$path/mk61s-M.ino.bin" | tr -d '[:space:]')"
  [[ "$size" =~ ^[0-9]+$ && "$size" -le "$maximum_size" ]] ||
    fail "$label BIN size is invalid: $size/$maximum_size"
  local headroom=$((maximum_size - size))
  ((headroom >= minimum_headroom)) ||
    fail "$label Flash headroom too small: $headroom < $minimum_headroom bytes"
  printf '%s stock linker + LTO: %s/%s bytes (%s free, min %s), no unresolved RAM exports\n' \
    "$label" "$size" "$maximum_size" "$headroom" "$minimum_headroom"
}

# Resident proportional UTF-8 flow is shared by loadable BASIC and FOCAL. Keep
# a hard 1-KiB product margin after that user-visible service is linked.
compile_case F401 BLACKPILL_F401CC 262144 1024
compile_case F411 BLACKPILL_F411CE 524288 0
printf 'Stock-linker compile check: OK\n'
