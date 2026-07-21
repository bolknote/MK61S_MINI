#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 firmware.elf" >&2
  exit 2
fi

elf="$1"
if [[ ! -f "$elf" ]]; then
  echo "ELF not found: $elf" >&2
  exit 2
fi

nm_tool="${ARM_NONE_EABI_NM:-}"
if [[ -z "$nm_tool" ]]; then
  nm_tool="$(command -v arm-none-eabi-nm || true)"
fi
if [[ -z "$nm_tool" ]]; then
  for arduino_data in "${ARDUINO_DATA_DIR:-}" \
                      "${HOME}/.arduino15" "${HOME}/Library/Arduino15"; do
    [[ -n "$arduino_data" ]] || continue
    nm_tool="$(find "$arduino_data/packages/STMicroelectronics/tools" \
      -type f -name arm-none-eabi-nm -print -quit 2>/dev/null || true)"
    [[ -z "$nm_tool" ]] || break
  done
fi
if [[ -z "$nm_tool" || ! -x "$nm_tool" ]]; then
  echo "arm-none-eabi-nm not found" >&2
  exit 2
fi

constructors="$("$nm_tool" --defined-only "$elf" |
  awk '$3 ~ /^_GLOBAL__sub_I_/ { print $3 }')"

# Эти объекты принадлежат STM32duino Core. Их время жизни задаёт фреймворк;
# проектные аппаратные объекты должны конструироваться явно из setup().
allowed='^_GLOBAL__sub_I_(SPI|SerialUSB|Serial[0-9]+|_Z22stm32_interrupt_enable7PinNameSt8functionIFvvEEm)$'
unexpected="$(printf '%s\n' "$constructors" | grep -Ev "$allowed" || true)"

if [[ -n "$unexpected" ]]; then
  echo "unexpected pre-setup C++ constructors:" >&2
  printf '  %s\n' $unexpected >&2
  exit 1
fi

echo "global constructor check: OK"
