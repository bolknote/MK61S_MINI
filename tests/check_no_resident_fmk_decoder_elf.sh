#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 firmware.elf" >&2
  exit 2
fi

elf="$1"
[[ -f "$elf" ]] || { echo "ELF not found: $elf" >&2; exit 2; }

find_arm_tool() {
  local variable_value="$1"
  local name="$2"
  local found="$variable_value"
  if [[ -z "$found" ]]; then found="$(command -v "$name" || true)"; fi
  if [[ -z "$found" ]]; then
    for arduino_data in "${ARDUINO_DATA_DIR:-}" \
                        "${HOME}/.arduino15" "${HOME}/Library/Arduino15"; do
      [[ -n "$arduino_data" ]] || continue
      found="$(find "$arduino_data/packages/STMicroelectronics/tools" \
        -type f -name "$name" -print -quit 2>/dev/null || true)"
      [[ -z "$found" ]] || break
    done
  fi
  [[ -n "$found" && -x "$found" ]] || {
    echo "$name not found" >&2
    exit 2
  }
  printf '%s\n' "$found"
}

nm_tool="$(find_arm_tool "${ARM_NONE_EABI_NM:-}" arm-none-eabi-nm)"
symbols="$($nm_tool -C --defined-only "$elf")"

# FMK1 is the compressed interchange format on C5.  Its parser, bit reader,
# CRC and RLE decoder belong exclusively to SETUP.APP.  The resident may keep
# bitmapPixel(): it is a format-neutral row-padded raster helper shared by the
# PFK1 renderer and costs far less than another copy under a new namespace.
unexpected="$({ grep -F 'fmk::' <<<"$symbols" || true; } |
  grep -Fv 'fmk::bitmapPixel(' || true)"
if [[ -n "$unexpected" ]]; then
  printf 'resident FMK decoder ELF check: compressed-font code leaked into resident:\n%s\n' \
    "$unexpected" >&2
  exit 1
fi

echo 'resident FMK decoder ELF check: OK'
