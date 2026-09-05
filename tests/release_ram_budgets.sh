#!/usr/bin/env bash

# Canonical values live in the release contract.  This compatibility shim is
# sourced by the existing RAM comparator while keeping shell arithmetic simple.
_mk61_contract_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_mk61_contract="$_mk61_contract_root/tools/release_contract.py"
readonly MK61_F401_WS0010_MAX_RAM_GROWTH="$(
  python3 "$_mk61_contract" comparison --key f401_ws0010_ram_growth)"
readonly MK61_F411_WS0010_MAX_RAM_GROWTH="$(
  python3 "$_mk61_contract" comparison --key f411_ws0010_ram_growth)"
readonly MK61_F401_WS0010_USB_MAX_RAM_GROWTH="$(
  python3 "$_mk61_contract" comparison --key f401_ws0010_usb_ram_growth)"
readonly MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH="$(
  python3 "$_mk61_contract" comparison --key f401_ws0010_graphics_ram_growth)"
unset _mk61_contract _mk61_contract_root
