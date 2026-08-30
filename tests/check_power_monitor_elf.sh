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
objdump_tool="$(find_arm_tool \
  "${ARM_NONE_EABI_OBJDUMP:-}" arm-none-eabi-objdump)"

symbols="$($nm_tool -S --defined-only "$elf")"
table="$($objdump_tool -t "$elf")"

irq_type="$(printf '%s\n' "$symbols" |
  awk '$4 == "PVD_IRQHandler" && !found {value=$3; found=1}
       END {if(found) print value}')"
[[ "$irq_type" == T ]] || {
  echo "PVD_IRQHandler must be a strong text symbol; found '$irq_type'" >&2
  exit 1
}

irq_size_hex="$(printf '%s\n' "$symbols" |
  awk '$4 == "PVD_IRQHandler" && !found {value=$2; found=1}
       END {if(found) print value}')"
[[ -n "$irq_size_hex" ]] || {
  echo 'PVD_IRQHandler size is unavailable' >&2
  exit 1
}
(( 16#$irq_size_hex <= 128 )) || {
  echo "PVD handler is unexpectedly large: 0x$irq_size_hex" >&2
  exit 1
}

handler='_ZN13power_monitor17interrupt_handlerEv'
handler_size_hex="$(printf '%s\n' "$symbols" |
  awk -v name="$handler" '$4 == name && !found {value=$2; found=1}
       END {if(found) print value}')"
if [[ -n "$handler_size_hex" ]]; then
  (( 16#$handler_size_hex <= 128 )) || {
    echo "PVD interrupt handler is unexpectedly large: 0x$handler_size_hex" >&2
    exit 1
  }
fi

printf '%s\n' "$table" |
  awk '$NF == "mk61_power_monitor_breadcrumb" &&
       $0 ~ /[[:space:]]\.noinit[^[:space:]]*[[:space:]]/ {found=1}
       END {exit !found}' || {
    echo 'PVD breadcrumb is not retained in .noinit' >&2
    exit 1
  }

handler_disassembly="$($objdump_tool -d --disassemble=PVD_IRQHandler "$elf")"
if [[ -n "$handler_size_hex" ]]; then
  handler_disassembly="$handler_disassembly
$($objdump_tool -d --disassemble="$handler" "$elf")"
fi
if printf '%s\n' "$handler_disassembly" |
    grep -Eq 'Serial|virtual_fat|program_store|SpiNorFlash|external_flash'; then
  echo 'PVD interrupt handler calls a forbidden high-level service' >&2
  exit 1
fi

echo 'power monitor ELF check: OK'
