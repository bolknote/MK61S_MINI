#!/usr/bin/env bash
set -euo pipefail
image=${1:?expected resident BIN path}
[ -s "$image" ] || { printf 'resident image not found: %s\n' "$image" >&2; exit 1; }
programmer=${MK61_STM32_PROGRAMMER:-}
if [ -z "$programmer" ]; then programmer=$(command -v STM32_Programmer_CLI || true); fi
if [ -n "$programmer" ]; then
  "$programmer" --connect port=usb1 VID=0x0483 PID=0xdf11 \
    --download "$image" 0x8000000 --verify --start 0x8000000
elif command -v dfu-util >/dev/null 2>&1; then
  dfu-util -d 0483:df11 -a 0 -s 0x08000000:leave -D "$image"
else
  printf '%s\n' 'Install STM32CubeProgrammer or dfu-util; set MK61_STM32_PROGRAMMER if it is not on PATH.' >&2
  exit 1
fi
