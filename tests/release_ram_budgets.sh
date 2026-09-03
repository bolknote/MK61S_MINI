#!/usr/bin/env bash

# Canonical static-RAM growth budgets shared by local release preflight and
# GitHub Actions. Keep every comparison explicit: an omitted policy must fail
# instead of silently falling back to zero after a feature is qualified.
readonly MK61_F401_WS0010_MAX_RAM_GROWTH=0
readonly MK61_F411_WS0010_MAX_RAM_GROWTH=256
readonly MK61_F401_WS0010_USB_MAX_RAM_GROWTH=0
# The code-only graphics API must not add persistent buffers. GCC LTO can
# change aggregate data/bss alignment between the two builds, even with
# per-object sections. Keep the existing 16-byte ceiling for that padding
# rather than depending on one particular partition layout.
readonly MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH=16
