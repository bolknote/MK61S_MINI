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

require_text_symbol() {
  local pattern="$1"
  local label="$2"
  grep -Eq "[[:space:]]T[[:space:]]${pattern}$" <<<"$symbols" || {
      printf 'USB suspend ELF check: missing strong %s\n' "$label" >&2
      exit 1
    }
}

forbid_symbol() {
  local pattern="$1"
  local label="$2"
  if grep -Eq "[[:space:]][TtWw][[:space:]]${pattern}$" <<<"$symbols"; then
    printf 'USB suspend ELF check: forbidden %s\n' "$label" >&2
    exit 1
  fi
}

for callback in \
  SetupStage Reset Suspend Resume DevConnected DevDisconnected; do
  require_text_symbol "__wrap_USBD_LL_${callback}" \
    "USBD_LL_${callback} linker wrapper"
  require_text_symbol "USBD_LL_${callback}" \
    "USBD_LL_${callback} wrapped implementation"
done

require_text_symbol 'usb_power::prepare_stop\(bool, unsigned long\)' \
  'USB STOP preparation path'
require_text_symbol 'usb_power::finish_stop\(bool, bool\)' \
  'USB STOP recovery path'
require_text_symbol 'usb_power::stop_wake_pending\(\)' \
  'USB wake-source classifier'
require_text_symbol 'OTG_FS_WKUP_IRQHandler' \
  'USB OTG FS wake interrupt'

forbid_symbol 'usb_power::advertise_remote_wakeup\(\)' \
  'remote-wakeup descriptor patch'
forbid_symbol 'HAL_PCD_ActivateRemoteWakeup' \
  'HAL remote-wakeup signal'
forbid_symbol 'HAL_PCD_DeActivateRemoteWakeup' \
  'HAL remote-wakeup release'

echo 'USB suspend ELF check: OK'
