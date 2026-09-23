#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"
contract="$root/tools/release_contract.py"

fail() {
  printf 'F411 release matrix: %s\n' "$1" >&2
  exit 2
}

command -v "$arduino_cli" >/dev/null 2>&1 ||
  fail "arduino-cli is not installed: $arduino_cli"
command -v python3 >/dev/null 2>&1 ||
  fail "python3 is required for the stack-usage release gate"
command -v c++ >/dev/null 2>&1 ||
  fail "a host C++17 compiler is required for the APP packer"
python3 "$contract" validate >/dev/null ||
  fail 'release contract is invalid'
expected_cli_version="$(python3 "$contract" toolchain --field arduino_cli)"
expected_core_version="$(python3 "$contract" toolchain --field stm32_core)"
expected_lcd_version="$(python3 "$contract" toolchain --field 'library:LiquidCrystal')"
expected_rtc_version="$(python3 "$contract" toolchain --field 'library:STM32duino RTC')"

cli_version="$("$arduino_cli" version 2>/dev/null || true)"
printf '%s\n' "$cli_version" |
  grep -Eq "Version:[[:space:]]+$expected_cli_version([[:space:]]|$)" ||
  fail "arduino-cli $expected_cli_version is required"

"$arduino_cli" core list |
  grep -Eq "^STMicroelectronics:stm32[[:space:]]+$expected_core_version([[:space:]]|$)" ||
  fail "STM32 Core $expected_core_version is required"
"$arduino_cli" lib list |
  grep -Eq "^LiquidCrystal[[:space:]]+$expected_lcd_version([[:space:]]|$)" ||
  fail "LiquidCrystal $expected_lcd_version is required"
"$arduino_cli" lib list |
  grep -Eq "^STM32duino RTC[[:space:]]+$expected_rtc_version([[:space:]]|$)" ||
  fail "STM32duino RTC $expected_rtc_version is required"

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
  command -v zip >/dev/null 2>&1 || fail 'zip is required for release bundles'
  # Published F411 bundles need the same complete notices as F401 bundles.
  python3 "$root/tools/.fmk-font/package_ui_font_licenses.py" \
    --archive "$output_dir/UI_FONT_LICENSES.zip"
fi

fqbn='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=osstd'
# LTO is qualified with the same size-oriented optimization policy as the
# release build.  The old o3lto probe already occupied 520964/524288 bytes at
# the plan-hard baseline, so it had no safe growth margin and was not a viable
# release configuration even before new features were added.
fqbn_lto='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=oslto'
strict_flags='-DMK61_ENABLE_LOADABLE_MODULES=1 -DMK61_REQUIRE_RESIDENT_CRC=1 -DMK61_REQUIRE_F411_SELECTIVE_O3=1 -Werror -Wno-error=cpp'
platform_ram_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'
variant_index=0
variant_count="$(python3 "$contract" cases --group f411-release --format count)"

layout_properties="$matrix_root/layout.properties"
"$arduino_cli" compile --fqbn "$fqbn" \
  --build-path "$matrix_root/properties-layout" \
  --show-properties=expanded "$sketch" > "$layout_properties"
variant_path="$(sed -n 's/^build\.variant\.path=//p' "$layout_properties" | tr -d '\r')"
ld_name="$(sed -n 's/^build\.ldscript=//p' "$layout_properties" | tr -d '\r')"
[[ -n "$variant_path" && -n "$ld_name" && -f "$variant_path/$ld_name" ]] ||
  fail 'cannot resolve the STM32F411 linker script'
portable_linker="$matrix_root/mk61-portable.ld"
python3 "$root/tools/.mk61-gcc/portable-layout.py" \
  "$variant_path/$ld_name" "$portable_linker"

define_value() {
  local flags="$1" macro="$2" value="$3" token
  for token in $flags; do
    case "$token" in
      -D"$macro"=*) value="${token#*=}" ;;
    esac
  done
  printf '%s' "$value"
}

package_system_apps() {
  local profile="$1" board_flags="$2" artifact_name="$3" build_path="$4"
  local expect_ws0010_graphics="$5"
  local focal basic markdown wbmp chip8 usb graphics ui_fonts bundle_name bundle
  focal="$(define_value "$board_flags" MK61_ENABLE_FOCAL 1)"
  basic="$(define_value "$board_flags" MK61_ENABLE_TINYBASIC 1)"
  markdown="$(define_value "$board_flags" MK61_ENABLE_MARKDOWN_VIEWER 1)"
  chip8="$(define_value "$board_flags" MK61_ENABLE_CHIP8 0)"
  usb="$(define_value "$board_flags" MK61_ENABLE_USB_SCREEN 0)"
  graphics="$usb"
  ui_fonts=0
  case "$profile" in
    classic-v2|classic-v3|40th) graphics=1; ui_fonts=1 ;;
    mini-v3-ws0010)
      if [[ "$expect_ws0010_graphics" == 1 ]]; then graphics=1; fi
      ;;
  esac
  wbmp="$(define_value "$board_flags" MK61_ENABLE_WBMP_VIEWER \
    "$([[ "$graphics" == 1 && "$markdown" == 0 ]] && printf 1 || printf 0)")"
  bundle_name="${artifact_name}-${firmware_tag}"
  bundle="$output_dir/$bundle_name"
  rm -rf "$bundle"
  mkdir -p "$bundle/System"
  python3 "$root/tools/build_system_app_bundle.py" \
    --resident-elf "$build_path/mk61s-M.ino.elf" \
    --compile-commands "$build_path/compile_commands.json" \
    --output-dir "$bundle/System" \
    --setup 0 \
    --usbdisk 0 \
    --graphics "$graphics" --ui-fonts "$ui_fonts" \
    --focal "$focal" --basic "$basic" --wbmp "$wbmp" \
    --markdown "$markdown" --chip8 "$chip8"
  cp "$build_path/mk61s-M.ino.bin" "$bundle/$bundle_name.bin"
  printf '%s\n' "$board_flags $platform_ram_flags $strict_flags" > "$bundle/build.flags"
  printf 'format 1\nabi 6\n' > "$bundle/build.apps"
  local expected=()
  [[ "$focal" == 0 ]] || expected+=(FOCAL.APP)
  [[ "$basic" == 0 ]] || expected+=(BASIC.APP)
  [[ "$wbmp" == 0 || "$markdown" == 1 ]] || expected+=(WBMP.APP)
  [[ "$markdown" == 0 ]] || expected+=(MARKDOWN.APP)
  [[ "$chip8" == 0 ]] || expected+=(CHIP8.APP)
  local file wanted expected_file
  for file in "${expected[@]}" HELP0.TXT HELP1.TXT; do
    [[ -s "$bundle/System/$file" ]] ||
      fail "missing product artifact: $bundle_name/System/$file"
  done
  for file in FOCAL.APP BASIC.APP WBMP.APP MARKDOWN.APP CHIP8.APP SETUP.APP \
      USBDISK.APP; do
    wanted=0
    for expected_file in "${expected[@]}"; do
      [[ "$file" != "$expected_file" ]] || wanted=1
    done
    [[ "$wanted" == 1 || ! -e "$bundle/System/$file" ]] ||
      fail "disabled APP was packaged: $bundle_name/System/$file"
  done
  for file in "${expected[@]}"; do
    python3 - "$bundle/System/$file" <<'PY'
from pathlib import Path
import struct
import sys

data = Path(sys.argv[1]).read_bytes()
assert len(data) >= 64 and data[:8] == b"MK61APP\0", "APP header"
assert struct.unpack_from("<H", data, 12)[0] == 6, "APP must use ABI 6"
assert struct.unpack_from("<I", data, 16)[0] in (5, 7), "relocatable flags"
assert struct.unpack_from("<I", data, 20)[0] == 0x20000000, "virtual link base"
stored = struct.unpack_from("<I", data, 24)[0]
memory = struct.unpack_from("<I", data, 32)[0]
code_size, relocations = struct.unpack_from("<II", data, 40)
assert len(data) == 64 + stored and memory <= 20 * 1024, "container size"
assert 0 < code_size <= stored and relocations <= stored - code_size, "relocation tail"
PY
  done
  (cd "$output_dir" && zip -qr "$bundle_name.zip" "$bundle_name")
}

compile_variant() {
  local case_id="$1"
  local profile="$2"
  local optimization="$3"
  local board_flags="$4"
  local artifact_name="$5"
  local flash_capacity="$6"
  local minimum_flash_headroom="$7"
  local stack_frame_limit="$8"
  local publish="$9"
  local expect_usb_suspend="${10}"
  local expect_ws0010_graphics="${11}"
  local name="${case_id#f411-}"
  local variant_fqbn="$fqbn"
  if [[ "$optimization" == oslto ]]; then
    variant_fqbn="$fqbn_lto"
  fi
  local build_path="$matrix_root/build-$name"
  local compile_log="$build_path/compile.log"
  local stack_summary="$build_path/stack-usage.json"
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
    --build-property "compiler.c.elf.extra_flags=-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected -Wl,--default-script=$portable_linker" \
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
  python3 "$root/tests/analyze_stack_usage.py" \
    --compile-commands "$build_path/compile_commands.json" \
    --source-root "$build_path/sketch" --top 3 \
    --max-frame "$stack_frame_limit" --summary-json "$stack_summary"
  local flash_line flash_max
  flash_line="$(grep -E '^Sketch uses [0-9]+ bytes .*Maximum is [0-9]+ bytes\.$' \
    "$compile_log" | tail -n 1)"
  [[ -n "$flash_line" ]] ||
    fail "could not parse Flash usage for $name"
  flash_max="$(sed -E 's/^.*Maximum is ([0-9]+) bytes\.$/\1/' <<<"$flash_line")"
  [[ "$flash_max" -eq "$flash_capacity" ]] ||
    fail "Flash capacity differs from contract for $name: $flash_max != $flash_capacity"
  test -s "$build_path/mk61s-M.ino.elf" ||
    fail "missing ELF for $name"
  test -s "$build_path/mk61s-M.ino.bin" ||
    fail "missing BIN for $name"
  "$root/tools/seal-firmware.sh" seal --max-size "$flash_capacity" \
    "$build_path/mk61s-M.ino.bin"
  "$root/tools/seal-firmware.sh" check --max-size "$flash_capacity" \
    "$build_path/mk61s-M.ino.bin"
  python3 "$contract" resource-report \
    --case "$case_id" \
    --elf "$build_path/mk61s-M.ino.elf" \
    --bin "$build_path/mk61s-M.ino.bin" \
    --compile-commands "$build_path/compile_commands.json" \
    --stack-summary "$stack_summary" \
    --output-prefix "$build_path/resource-report"
  "$root/tests/check_global_constructors.sh" \
    "$build_path/mk61s-M.ino.elf"
  python3 "$root/tests/check_app_memory_elf.py" \
    "$build_path/mk61s-M.ino.elf"
  "$root/tests/check_early_dfu_elf.sh" \
    "$build_path/mk61s-M.ino.elf"
  "$root/tests/check_core_native_hot_paths_elf.sh" \
    "$build_path/mk61s-M.ino.elf"
  "$root/tests/check_no_resident_fmk_decoder_elf.sh" --allow-fmk \
    --allow-usbdisk \
    "$build_path/mk61s-M.ino.elf"
  "$root/tests/check_power_monitor_elf.sh" \
    "$build_path/mk61s-M.ino.elf"
  "$root/tests/check_rtc_alarm_elf.sh" \
    "$build_path/mk61s-M.ino.elf"
  if [[ "$expect_usb_suspend" == 1 ]]; then
    "$root/tests/check_usb_suspend_elf.sh" \
      "$build_path/mk61s-M.ino.elf"
  else
    "$root/tests/check_usb_suspend_elf.sh" --disabled \
      "$build_path/mk61s-M.ino.elf"
  fi
  if [[ "$expect_ws0010_graphics" != - ]]; then
    if [[ "$expect_ws0010_graphics" == 0 ]]; then
      "$root/tests/check_ws0010_graphics_elf.sh" --disabled \
        "$build_path/mk61s-M.ino.elf"
    else
      "$root/tests/check_ws0010_graphics_elf.sh" \
        "$build_path/mk61s-M.ino.elf"
    fi
  fi
  if [[ -n "$output_dir" && "$publish" == 1 ]]; then
    cp "$build_path/mk61s-M.ino.bin" \
      "$output_dir/${artifact_name}-${firmware_tag}.bin"
    package_system_apps "$profile" "$board_flags" "$artifact_name" \
      "$build_path" "$expect_ws0010_graphics"
  fi
}

while IFS=$'\t' read -r \
    case_id profile optimization board_flags artifact_name \
    flash_capacity minimum_flash_headroom _ram_capacity _ram_limit \
    stack_frame_limit _product publish expect_usb_suspend \
    expect_ws0010_graphics _focal _basic _wbmp _markdown _chip8 \
    _usb_screen _ws0010_graphics _extended_font _user_explorer \
    _math_backend _lto; do
  compile_variant "$case_id" "$profile" "$optimization" "$board_flags" \
    "$artifact_name" "$flash_capacity" "$minimum_flash_headroom" \
    "$stack_frame_limit" "$publish" "$expect_usb_suspend" \
    "$expect_ws0010_graphics"
done < <(python3 "$contract" cases --group f411-release --format tsv)

printf '\nF411 strict release matrix: OK (%d variants)\n' "$variant_count"
