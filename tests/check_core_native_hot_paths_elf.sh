#!/usr/bin/env bash
set -euo pipefail

mode=enabled
if [[ "${1:-}" == "--disabled" ]]; then
  mode=disabled
  shift
fi
if [[ $# -ne 1 ]]; then
  echo "usage: $0 [--disabled] firmware.elf" >&2
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
native_wrapper=' IK1302_1303_Tick_All('

if [[ "$mode" == disabled ]]; then
  if grep -Fq "$native_wrapper" <<<"$symbols"; then
    echo 'core native-path ELF check: unexpected native wrapper' >&2
    exit 1
  fi
  echo 'core native-path ELF check: safely disabled'
  exit 0
fi

grep -Fq "$native_wrapper" <<<"$symbols" || {
  echo 'core native-path ELF check: native wrapper is missing' >&2
  exit 1
}
echo 'core native-path ELF check: OK'
