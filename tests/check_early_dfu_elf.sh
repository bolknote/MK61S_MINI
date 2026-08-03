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
  if [[ -z "$found" ]]; then
    found="$(command -v "$name" || true)"
  fi
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
objdump_tool="$(find_arm_tool "${ARM_NONE_EABI_OBJDUMP:-}" arm-none-eabi-objdump)"

symbols="$($nm_tool --defined-only "$elf")"
table="$($objdump_tool -t "$elf")"

require_symbol() {
  local name="$1"
  printf '%s\n' "$symbols" | awk -v symbol="$name" '$3 == symbol { found=1 } END { exit !found }' || {
    echo "early DFU symbol missing: $name" >&2
    exit 1
  }
}

require_symbol mk61_early_dfu_preinit
require_symbol mk61_early_dfu_preinit_slot
require_symbol mk61_early_dfu_request

printf '%s\n' "$table" |
  awk '$NF == "mk61_early_dfu_preinit_slot" && $0 ~ /[[:space:]]\.preinit_array[[:space:]]/ { found=1 } END { exit !found }' || {
    echo 'early DFU hook is not in .preinit_array' >&2
    exit 1
  }

printf '%s\n' "$table" |
  awk '$NF == "mk61_early_dfu_request" && $0 ~ /[[:space:]]\.noinit[^[:space:]]*[[:space:]]/ { found=1 } END { exit !found }' || {
    echo 'early DFU request is not retained in a .noinit section' >&2
    exit 1
  }

if printf '%s\n' "$symbols" | awk '$3 == "mk61_dfu_reboot_request" { found=1 } END { exit !found }'; then
  echo 'legacy retained DFU request is still linked' >&2
  exit 1
fi

init_type="$(printf '%s\n' "$symbols" | awk '$3 == "init" { print $2; exit }')"
if [[ -n "$init_type" && "$init_type" != "W" && "$init_type" != "w" ]]; then
  echo "STM32duino init() must remain weak or be eliminated by LTO; found type '$init_type'" >&2
  exit 1
fi

echo 'early DFU ELF check: OK'
