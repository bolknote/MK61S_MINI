#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
contract="$root/tools/release_contract.py"

fail() {
  printf 'F411 release matrix: %s\n' "$1" >&2
  exit 2
}

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v c++ >/dev/null 2>&1 || fail "a host C++17 compiler is required"
python3 "$contract" validate >/dev/null || fail 'release contract is invalid'
python3 "$root/tools/.mk61-gcc/build-standalone.py" --profile classic-v3 \
  --build-path "$root/.build/native-preflight" --check
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

strict_flags='-DMK61_NATIVE_RUNTIME=1 -DMK61_ENABLE_LOADABLE_MODULES=1 -DMK61_REQUIRE_RESIDENT_CRC=1 -DMK61_REQUIRE_F411_SELECTIVE_O3=1 -Werror -Wno-error=cpp'
platform_ram_flags=''
variant_index=0
variant_count="$(python3 "$contract" cases --group f411-release --format count)"

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
  local focal basic markdown wbmp chip8 setup usb external_usbdisk graphics ui_fonts
  local focal_app basic_app wbmp_app markdown_app chip8_app setup_app explorer_app
  local bundle_name bundle
  focal="$(define_value "$board_flags" MK61_ENABLE_FOCAL 1)"
  basic="$(define_value "$board_flags" MK61_ENABLE_TINYBASIC 1)"
  markdown="$(define_value "$board_flags" MK61_ENABLE_MARKDOWN_VIEWER 1)"
  chip8="$(define_value "$board_flags" MK61_ENABLE_CHIP8 0)"
  focal_app="$(define_value "$board_flags" MK61_FOCAL_AS_APP 1)"
  basic_app="$(define_value "$board_flags" MK61_TINYBASIC_AS_APP "$focal")"
  wbmp_app="$(define_value "$board_flags" MK61_WBMP_VIEWER_AS_APP 0)"
  markdown_app="$(define_value "$board_flags" MK61_MARKDOWN_VIEWER_AS_APP 0)"
  chip8_app="$(define_value "$board_flags" MK61_CHIP8_AS_APP 0)"
  setup="$(define_value "$board_flags" MK61_ENABLE_SETUP 1)"
  setup_app="$(define_value "$board_flags" MK61_SETUP_AS_APP 0)"
  explorer_app="$(define_value "$board_flags" MK61_EXPLORER_AS_APP 0)"
  usb="$(define_value "$board_flags" MK61_ENABLE_USB_SCREEN 0)"
  external_usbdisk="$(define_value "$board_flags" \
    MK61_EXTERNALIZE_USBDISK 0)"
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
    --setup "$((setup * setup_app))" \
    --usbdisk "$external_usbdisk" \
    --explorer "$explorer_app" \
    --graphics "$graphics" --ui-fonts "$ui_fonts" \
    --focal "$((focal * focal_app))" \
    --basic "$((basic * basic_app))" \
    --wbmp "$((wbmp * wbmp_app))" \
    --markdown "$((markdown * markdown_app))" \
    --chip8 "$((chip8 * chip8_app))" \
    --catalog-dir "$output_dir/apps/abi6"
  cp "$build_path/mk61s-M.ino.bin" "$bundle/$bundle_name.bin"
  cp "$build_path/mk61s-M.ino.elf" "$bundle/$bundle_name.elf"
  printf '%s\n' "$board_flags $platform_ram_flags $strict_flags" > "$bundle/build.flags"
  printf 'format 1\nabi 6\n' > "$bundle/build.apps"
  local expected=()
  [[ "$focal" == 0 || "$focal_app" == 0 ]] || expected+=(FOCAL.APP)
  [[ "$basic" == 0 || "$basic_app" == 0 ]] || expected+=(BASIC.APP)
  [[ "$wbmp" == 0 || "$wbmp_app" == 0 || "$markdown" == 1 ]] || expected+=(WBMP.APP)
  [[ "$markdown" == 0 || "$markdown_app" == 0 ]] || expected+=(MARKDOWN.APP)
  [[ "$chip8" == 0 || "$chip8_app" == 0 ]] || expected+=(CHIP8.APP)
  [[ "$setup" == 0 || "$setup_app" == 0 ]] || expected+=(SETUP.APP)
  [[ "$external_usbdisk" == 0 ]] || expected+=(USBDISK.APP)
  [[ "$explorer_app" == 0 ]] || expected+=(EXPLORER.APP)
  local resident_vm overlay_vm
  resident_vm="$(define_value "$board_flags" MK61_RESIDENT_LANGUAGE_VM 0)"
  overlay_vm="$(define_value "$board_flags" MK61_OVERLAY_LANGUAGE_VM "$((focal && !resident_vm))")"
  [[ "$overlay_vm" == 0 ]] || expected+=(LANGVM.APP LANGIN.APP)
  # The ELF selects helper packaging, including explicit no-cache overrides.
  local helper_policy
  helper_policy="$(python3 - "$build_path/mk61s-M.ino.elf" "$root/tools" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
from build_system_app_bundle import run, compiler_from_database
elf=Path(sys.argv[1]);toolchain=compiler_from_database(elf.parent/'compile_commands.json').parent
symbols=run([toolchain/'arm-none-eabi-nm','--defined-only',elf],capture=True)
import re
m=re.search(r'^([0-9a-fA-F]+)\s+A\s+mk61_vm_file_cache_enabled\s*$',symbols,re.M)
mode=int(m[1],16) if m else 0
assert mode in (0,1)
print(mode)
PY
)"
  [[ "$helper_policy" == 0 || ( "$basic" == 0 && "$focal" == 0 ) ]] || expected+=(VMCache/VMSTORE.APP)
  local file wanted expected_file
  for file in "${expected[@]}" HELP0.TXT HELP1.TXT; do
    [[ -s "$bundle/System/$file" ]] ||
      fail "missing product artifact: $bundle_name/System/$file"
  done
  for file in FOCAL.APP BASIC.APP WBMP.APP MARKDOWN.APP CHIP8.APP SETUP.APP \
      USBDISK.APP EXPLORER.APP LANGVM.APP LANGIN.APP VMCache/VMSTORE.APP; do
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
  local build_path="$matrix_root/build-$name"
  local compile_log="$build_path/compile.log"
  local stack_summary="$build_path/stack-usage.json"
  variant_index=$((variant_index + 1))
  printf '\n[%d/%d] Native F411 %s\n' "$variant_index" "$variant_count" "$name"
  mkdir -p "$build_path"
  python3 "$root/tools/.mk61-gcc/build-standalone.py" \
    --release-case "$case_id" --build-path "$build_path" \
    --jobs "${MK61_BUILD_JOBS:-4}" 2>&1 | tee "$compile_log"
  # ELF gates use the same independent binutils as the actual native build.
  local tool_bin
  tool_bin="$(python3 - "$build_path/compile_commands.json" "$root/tools" <<'PYTOOLS'
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
from release_contract import discover_binutils
print(discover_binutils(Path(sys.argv[1]))[1].parent)
PYTOOLS
)"
  export PATH="$tool_bin:$PATH"
  # Stable legacy artifact aliases preserve cross-MCU release/report consumers.
  cp "$build_path/resident.elf" "$build_path/mk61s-M.ino.elf"
  cp "$build_path/resident.bin" "$build_path/mk61s-M.ino.bin"
  python3 "$root/tests/check_standalone_sdk_build.py" "$build_path/compile_commands.json"
  python3 "$root/tests/check_stm32_standalone_build.py" "$build_path/compile_commands.json"
  python3 "$root/tests/check_native_runtime_libraries.py" "$build_path/resident.map" --without-libc
  python3 "$root/tests/check_core_lto_objects.py" \
    --compile-commands "$build_path/compile_commands.json"
  python3 "$root/tests/check_narrow_stm32_drivers_elf.py" "$build_path/mk61s-M.ino.elf"
  python3 "$root/tests/check_compiler_warnings.py" \
    --log "$compile_log" \
    --compile-commands "$build_path/compile_commands.json"
  python3 "$root/tests/check_foreground_stack_elf.py" \
    "$build_path/mk61s-M.ino.elf" \
    --compile-commands "$build_path/compile_commands.json"
  python3 "$root/tests/analyze_stack_usage.py" \
    --compile-commands "$build_path/compile_commands.json" \
    --source-root "$root/code" --top 3 \
    --max-frame "$stack_frame_limit" --summary-json "$stack_summary"
  test -s "$build_path/mk61s-M.ino.elf" ||
    fail "missing ELF for $name"
  test -s "$build_path/mk61s-M.ino.bin" ||
    fail "missing BIN for $name"
  python3 "$root/tests/check_usb_cdc_rx_elf.py" \
    "$build_path/mk61s-M.ino.elf" \
    --compile-commands "$build_path/compile_commands.json"
  "$root/tools/seal-firmware.sh" seal --max-size "$flash_capacity" \
    "$build_path/mk61s-M.ino.bin"
  "$root/tools/seal-firmware.sh" check --max-size "$flash_capacity" \
    "$build_path/mk61s-M.ino.bin"
  python3 "$root/tools/seal-firmware-elf.py" \
    --bin "$build_path/mk61s-M.ino.bin" \
    --elf "$build_path/mk61s-M.ino.elf" \
    --compile-commands "$build_path/compile_commands.json"
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
  local external_usbdisk
  external_usbdisk="$(define_value "$board_flags" \
    MK61_EXTERNALIZE_USBDISK 0)"
  local fmk_check_flags=()
  if [[ "$(define_value "$board_flags" MK61_SETUP_AS_APP 0)" == 0 ]]; then
    fmk_check_flags=(--allow-fmk)
  fi
  if [[ "$external_usbdisk" == 1 ]]; then
    "$root/tests/check_no_resident_fmk_decoder_elf.sh" "${fmk_check_flags[@]}" \
      "$build_path/mk61s-M.ino.elf"
  else
    "$root/tests/check_no_resident_fmk_decoder_elf.sh" "${fmk_check_flags[@]}" \
      --allow-usbdisk "$build_path/mk61s-M.ino.elf"
  fi
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
    cp "$build_path/mk61s-M.ino.elf" \
      "$output_dir/${artifact_name}-${firmware_tag}.elf"
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
