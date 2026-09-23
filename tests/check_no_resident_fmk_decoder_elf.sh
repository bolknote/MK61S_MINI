#!/usr/bin/env bash
set -euo pipefail

allow_fmk=0
allow_usbdisk=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-fmk) allow_fmk=1; shift ;;
    --allow-usbdisk) allow_usbdisk=1; shift ;;
    *) break ;;
  esac
done
if [[ $# -ne 1 ]]; then
  echo "usage: $0 [--allow-fmk] [--allow-usbdisk] firmware.elf" >&2
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

# FMK decoding remains outside the tight F401 resident. F411 deliberately
# embeds SETUP, so its FMK parser is expected in the resident ELF.
if [[ "$allow_fmk" == 0 ]]; then
  unexpected="$({ grep -F 'fmk::' <<<"$symbols" || true; } |
    grep -Fv 'fmk::bitmapPixel(' || true)"
  if [[ -n "$unexpected" ]]; then
    printf 'resident FMK decoder ELF check: compressed-font code leaked into resident:\n%s\n' \
      "$unexpected" >&2
    exit 1
  fi
fi

# FAT12 directory synthesis, LFN conversion and the transactional import plan
# belong to USBDISK.APP on F401. F411 deliberately embeds the same sources.
if [[ "$allow_usbdisk" == 0 ]]; then
  fat_unexpected="$({ grep -E \
    'virtual_fat::.*(render_node_dirent|walk_directory|parse_lfn|apply_file|process_node|prune_tree|ensure_all_directory_extents)' \
    <<<"$symbols" || true; })"
  if [[ -n "$fat_unexpected" ]]; then
    printf 'resident USBDISK ELF check: FAT/LFN implementation leaked into resident:\n%s\n' \
      "$fat_unexpected" >&2
    exit 1
  fi
else
  fat_present="$({ grep -E \
    'virtual_fat::.*(walk_directory|parse_lfn|prune_tree|ensure_all_directory_extents)' \
    <<<"$symbols" || true; })"
  if [[ -z "$fat_present" ]]; then
    echo 'resident USBDISK ELF check: F411 FAT/LFN implementation is missing' >&2
    exit 1
  fi
fi

echo 'resident FMK/USBDISK payload ELF check: OK'
