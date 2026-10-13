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
cxxfilt_tool="$(find_arm_tool "${ARM_NONE_EABI_CXXFILT:-}" arm-none-eabi-c++filt)"
# GCC LTO can promote private state and append .lto_priv.N. Remove only that
# generated suffix before demangling, including in the disabled-profile gate.
symbols="$("$nm_tool" --defined-only "$elf" |
  sed -E 's/\.lto_priv\.[0-9]+$//' | "$cxxfilt_tool")"

require_text_symbol() {
  local pattern="$1"
  local label="$2"
  grep -Eq "[[:space:]]T[[:space:]]${pattern}$" <<<"$symbols" || {
      printf 'USB suspend ELF check: missing strong %s\n' "$label" >&2
      exit 1
    }
}

require_data_symbol() {
  local pattern="$1"
  local label="$2"
  grep -Eq "[[:space:]][BbDd][[:space:]]${pattern}$" <<<"$symbols" || {
    printf 'USB suspend ELF check: missing %s\n' "$label" >&2
    exit 1
  }
}

forbid_data_symbol() {
  local pattern="$1"
  local label="$2"
  if grep -Eq "[[:space:]][BbDd][[:space:]]${pattern}$" <<<"$symbols"; then
    printf 'USB suspend ELF check: unexpected %s\n' "$label" >&2
    exit 1
  fi
}

forbid_symbol() {
  local pattern="$1"
  local label="$2"
  if grep -Eq "[[:space:]][TtWw][[:space:]]${pattern}$" <<<"$symbols"; then
    printf 'USB suspend ELF check: forbidden %s\n' "$label" >&2
    exit 1
  fi
}

if [[ "$mode" == disabled ]]; then
  # The STM32 core owns a strong OTG_FS_WKUP_IRQHandler in every USB build.
  # These private state objects, in contrast, exist only when our preserving
  # STOP and automatic controller were actually compiled.
  forbid_data_symbol \
    'deep_idle::\(anonymous namespace\)::automatic_controller' \
    'automatic STOP controller in disabled profile'
  forbid_data_symbol \
    'usb_power::\(anonymous namespace\)::stop_arms' \
    'USB STOP accounting in disabled profile'
  echo 'USB suspend ELF check: safely disabled'
  exit 0
fi

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

objdump_tool="$(find_arm_tool \
  "${ARM_NONE_EABI_OBJDUMP:-}" arm-none-eabi-objdump)"
disassembly="$("$objdump_tool" -d -C "$elf")"
sized_symbols="$("$nm_tool" -S --defined-only "$elf")"

require_called_boundary() {
  local pattern="$1"
  local mangled="$2"
  local minimum_size="$3"
  local label="$4"
  grep -Eq "[[:space:]](bl|blx|b\\.w)[[:space:]][^<]*<${pattern}>" \
    <<<"$disassembly" || {
      printf 'USB suspend ELF check: no actual call to %s\n' "$label" >&2
      exit 1
    }
  local size_hex
  size_hex="$(awk -v name="$mangled" '$4 == name {print $2; exit}' \
    <<<"$sized_symbols")"
  [[ -n "$size_hex" ]] && ((16#$size_hex >= minimum_size)) || {
    printf 'USB suspend ELF check: empty or trivial %s\n' "$label" >&2
    exit 1
  }
}

require_called_boundary 'usb_power::prepare_stop\(bool, unsigned long\)' \
  '_ZN9usb_power12prepare_stopEbm' 32 'USB STOP preparation path'
require_called_boundary 'usb_power::finish_stop\(bool, bool\)' \
  '_ZN9usb_power11finish_stopEbb' 16 'USB STOP recovery path'
require_called_boundary 'usb_power::stop_wake_pending\(\)' \
  '_ZN9usb_power17stop_wake_pendingEv' 8 'USB wake-source classifier'
require_data_symbol \
  'deep_idle::\(anonymous namespace\)::automatic_controller' \
  'automatic STOP controller'
require_data_symbol \
  'usb_power::\(anonymous namespace\)::stop_arms' \
  'USB STOP accounting'

forbid_symbol 'usb_power::advertise_remote_wakeup\(\)' \
  'remote-wakeup descriptor patch'
forbid_symbol 'HAL_PCD_ActivateRemoteWakeup' \
  'HAL remote-wakeup signal'
forbid_symbol 'HAL_PCD_DeActivateRemoteWakeup' \
  'HAL remote-wakeup release'

echo 'USB suspend ELF check: OK'
