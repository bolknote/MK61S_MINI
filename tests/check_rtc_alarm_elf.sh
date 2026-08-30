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

require_text_symbol() {
  local pattern="$1"
  printf '%s\n' "$symbols" |
    awk -v pattern="$pattern" '$3 ~ /^[Tt]$/ && $4 ~ pattern {found=1}
      END {exit !found}' || {
      echo "RTC alarm symbol missing: $pattern" >&2
      exit 1
    }
}

require_text_symbol '^RTC_Alarm_IRQHandler$'
# Whole-program LTO may inline schedule_after() and poll() into the terminal and
# foreground loop. The persisted hardware boundary itself must remain linked.
require_text_symbol 'rtc_clock.*schedule_alarm'

for callback in alarm_a_callback alarm_b_callback; do
  line="$(printf '%s\n' "$symbols" |
    awk -v callback="$callback" '$4 ~ callback && !found {
      print $2 " " $3 " " $4; found=1
    }')"
  [[ -n "$line" ]] || {
    echo "RTC callback missing: $callback" >&2
    exit 1
  }
  read -r size_hex symbol_type symbol_name <<<"$line"
  [[ "$symbol_type" == t || "$symbol_type" == T ]] || {
    echo "RTC callback is not text: $callback ($symbol_type)" >&2
    exit 1
  }
  (( 16#$size_hex <= 64 )) || {
    echo "RTC callback is unexpectedly large: $callback 0x$size_hex" >&2
    exit 1
  }
  callback_disassembly="$($objdump_tool -d --disassemble="$symbol_name" "$elf")"
  if printf '%s\n' "$callback_disassembly" |
      grep -Eq $'\t(?:bl|blx)(?:\.|\t|[[:space:]])'; then
    echo "RTC callback must only publish an atomic event bit: $callback" >&2
    exit 1
  fi
done

echo 'RTC alarm ELF check: OK'
