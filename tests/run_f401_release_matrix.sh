#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
contract="$root/tools/release_contract.py"

fail() {
  printf 'F401 release matrix: %s\n' "$1" >&2
  exit 2
}

command -v python3 >/dev/null 2>&1 || fail 'python3 is required'
python3 "$contract" validate >/dev/null || fail 'release contract is invalid'

temporary_root=0
if [[ -n "${MK61_F401_MATRIX_ROOT:-}" ]]; then
  matrix_root="$MK61_F401_MATRIX_ROOT"
  [[ ! -e "$matrix_root" ]] || fail "matrix root already exists: $matrix_root"
  mkdir -p "$matrix_root"
else
  matrix_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f401-matrix.XXXXXX")"
  temporary_root=1
fi

cleanup() {
  if [[ "$temporary_root" -eq 1 ]]; then
    rm -rf "$matrix_root"
  fi
}
trap cleanup EXIT HUP INT TERM

output_dir="${MK61_FIRMWARE_OUTPUT_DIR:-$matrix_root/firmware}"
mkdir -p "$output_dir"

build_group() {
  local group="$1"
  while IFS=$'\t' read -r \
      case_id profile _optimization _defines artifact flash_capacity \
      minimum_flash_headroom ram_capacity ram_limit stack_frame_limit \
      product publish _usb_suspend _expect_graphics focal basic wbmp \
      markdown chip8 usb_screen ws0010_graphics extended_font \
      user_explorer math_backend lto; do
    local case_root="$matrix_root/$case_id"
    local case_output="$matrix_root/output-$case_id"
    if [[ "$publish" == 1 ]]; then
      case_output="$output_dir"
    fi
    printf '\nF401 contract case: %s\n' "$case_id"
    MK61_COLOR=never "$root/tools/build-gcc.cmd" \
      -ReleaseCase "$case_id" \
      -Profile "$profile" \
      -Focal "$focal" \
      -Basic "$basic" \
      -Wbmp "$wbmp" \
      -Markdown "$markdown" \
      -Chip8 "$chip8" \
      -UsbScreen "$usb_screen" \
      -Ws0010Graphics "$ws0010_graphics" \
      -ExtendedFontSettings "$extended_font" \
      -UserExplorer "$user_explorer" \
      -MathBackend "$math_backend" \
      -Lto "$lto" \
      -BuildRoot "$case_root" \
      -OutputDirectory "$case_output"

    local build_path="$case_root/$profile"
    local elf="$build_path/resident.elf"
    [[ -s "$elf" ]] || fail "missing ELF for $case_id"
    "$root/tests/check_global_constructors.sh" "$elf"
    "$root/tests/check_early_dfu_elf.sh" "$elf"
    "$root/tests/check_usb_suspend_elf.sh" --disabled "$elf"
    if [[ "$profile" == mini-v3-ws0010 ]]; then
      "$root/tests/check_ws0010_graphics_elf.sh" --disabled "$elf"
    fi

    if [[ "$publish" == 1 ]]; then
      local bundle_root="$output_dir/$artifact"
      local resident="$bundle_root/$artifact.bin"
      [[ -s "$resident" ]] || fail "missing product BIN: $resident"
      "$root/tools/seal-firmware.sh" check --max-size "$flash_capacity" \
        "$resident"
      for file in build.flags build.apps System/FOCAL.APP System/BASIC.APP \
          System/MARKDOWN.APP; do
        [[ -s "$bundle_root/$file" ]] ||
          fail "missing product artifact: $artifact/$file"
      done
      for file in System/WBMP.APP System/CHIP8.APP; do
        [[ ! -e "$bundle_root/$file" ]] ||
          fail "disabled APP was packaged: $artifact/$file"
      done
      for file in System/FOCAL.APP System/BASIC.APP System/MARKDOWN.APP; do
        local codec
        codec="$(od -An -tu1 -j15 -N1 "$bundle_root/$file" | tr -d '[:space:]')"
        [[ "$codec" == 1 ]] || fail "System APP is not ZX0: $artifact/$file"
      done
      for flag in \
          '-DMK61_REQUIRE_RESIDENT_CRC=1' \
          "-DMK61_MATH_BACKEND=$math_backend" \
          "-DMK61_ENABLE_LTO=$lto"; do
        grep -Fq -- "$flag" "$bundle_root/build.flags" ||
          fail "missing build flag for $artifact: $flag"
      done
      local markdown_limit markdown_size
      markdown_limit="$(python3 "$contract" case --id "$case_id" --format json |
        python3 -c 'import json,sys; print(json.load(sys.stdin)["budgets"]["markdown_app_max"])')"
      markdown_size="$(wc -c < "$bundle_root/System/MARKDOWN.APP" | tr -d '[:space:]')"
      ((markdown_size <= markdown_limit)) ||
        fail "MARKDOWN.APP exceeds $markdown_limit bytes: $markdown_size"
    fi
  done < <(python3 "$contract" cases --group "$group" --format tsv)
}

build_group f401-product
build_group f401-capability

if [[ -n "${MK61_F411_MATRIX_ROOT:-}" ]]; then
  f411_root="$MK61_F411_MATRIX_ROOT"
  [[ -d "$f411_root" ]] || fail "F411 matrix root is missing: $f411_root"
  size_tool="$(awk -F= '/^CMAKE_SIZE:FILEPATH=/ {print $2; exit}' \
    "$matrix_root/f401-product-a00/mini-v3-a00/CMakeCache.txt")"
  "$root/tests/check_release_ws0010_ram.sh" "$size_tool" \
    "$matrix_root/f401-product-a00/mini-v3-a00/resident.elf" \
    "$matrix_root/f401-product-ws0010/mini-v3-ws0010/resident.elf" \
    "$f411_root/build-lcd1602-a00/mk61s-M.ino.elf" \
    "$f411_root/build-oled1602-ws0010/mk61s-M.ino.elf" \
    "$matrix_root/f401-capability-a00-usb/mini-v3-a00/resident.elf" \
    "$matrix_root/f401-capability-ws-usb/mini-v3-ws0010/resident.elf" \
    "$matrix_root/f401-capability-ws-usb-graphics/mini-v3-ws0010/resident.elf"
else
  printf 'F401 release matrix: WS0010 cross-MCU RAM comparison NOT_RUN ' >&2
  printf '(set MK61_F411_MATRIX_ROOT)\n' >&2
fi

python3 "$contract" aggregate-reports --reports-below "$matrix_root" \
  --output-prefix "$output_dir/F401_RESOURCE_REPORT"

if [[ "${MK61_PACKAGE_RELEASE:-0}" == 1 ]]; then
  command -v zip >/dev/null 2>&1 || fail 'zip is required for packaging'
  while IFS=$'\t' read -r \
      _case_id _profile _optimization _defines artifact _rest; do
    (cd "$output_dir" && zip -qr "$artifact.zip" "$artifact")
  done < <(python3 "$contract" cases --group f401-product --format tsv)
fi

printf '\nF401 release matrix: OK\n'
