#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/tests/release_ram_budgets.sh"

if [[ $# -ne 8 ]]; then
  printf '%s\n' \
    'usage: check_release_ws0010_ram.sh ARM_SIZE F401_A00 F401_WS0010 F411_A00 F411_WS0010 F401_A00_USB F401_WS0010_USB F401_WS0010_USB_GRAPHICS' >&2
  exit 2
fi

size_tool="$1"
f401_a00="$2"
f401_ws0010="$3"
f411_a00="$4"
f411_ws0010="$5"
f401_a00_usb="$6"
f401_ws0010_usb="$7"
f401_ws0010_usb_graphics="$8"

"$root/tests/check_ws0010_ram.sh" "$size_tool" \
  "$f401_a00" "$f401_ws0010" \
  "$MK61_F401_WS0010_MAX_RAM_GROWTH"
"$root/tests/check_ws0010_ram.sh" "$size_tool" \
  "$f411_a00" "$f411_ws0010" \
  "$MK61_F411_WS0010_MAX_RAM_GROWTH"
"$root/tests/check_ws0010_ram.sh" "$size_tool" \
  "$f401_a00_usb" "$f401_ws0010_usb" \
  "$MK61_F401_WS0010_USB_MAX_RAM_GROWTH"
"$root/tests/check_ws0010_ram.sh" "$size_tool" \
  "$f401_ws0010_usb" "$f401_ws0010_usb_graphics" \
  "$MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH"
