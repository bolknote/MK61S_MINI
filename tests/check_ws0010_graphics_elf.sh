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

readback_public='MK61Display::readWs0010GraphicsQualificationFrame(unsigned char*, unsigned int)'
readback_owned='MK61Display::readWs0010GraphicsFrameFor(ws0010::GraphicsOwner, unsigned char*, unsigned int)'
readback_terminal='class_terminal::display_test_graphics_readback(unsigned char)'

require_symbol() {
  local symbol="$1"
  grep -Fq " $symbol" <<<"$symbols" || {
    printf 'WS0010 graphics ELF check: missing %s\n' "$symbol" >&2
    exit 1
  }
}

forbid_symbol() {
  local symbol="$1"
  if grep -Fq " $symbol" <<<"$symbols"; then
    printf 'WS0010 graphics ELF check: unexpected %s\n' "$symbol" >&2
    exit 1
  fi
}

if [[ "$mode" == disabled ]]; then
  forbid_symbol "$readback_public"
  forbid_symbol "$readback_owned"
  forbid_symbol "$readback_terminal"
  echo 'WS0010 graphics ELF check: safely disabled'
  exit 0
fi

require_symbol "$readback_public"
require_symbol "$readback_owned"
require_symbol "$readback_terminal"
echo 'WS0010 graphics ELF check: OK'
