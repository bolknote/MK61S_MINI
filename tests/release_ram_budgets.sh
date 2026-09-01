#!/usr/bin/env bash

# Canonical static-RAM growth budgets shared by local release preflight and
# GitHub Actions. Keep every comparison explicit: an omitted policy must fail
# instead of silently falling back to zero after a feature is qualified.
readonly MK61_F401_WS0010_MAX_RAM_GROWTH=0
readonly MK61_F411_WS0010_MAX_RAM_GROWTH=256
readonly MK61_F401_WS0010_USB_MAX_RAM_GROWTH=0
# Enabling the code-only graphics API changes GCC LTO partitioning.  The
# resulting F401 image has the same BSS objects and object sizes, but consumes
# 16 more bytes in aggregate internal .bss alignment.  Keep the allowance exact
# so a real persistent graphics allocation still fails the release gate.
readonly MK61_F401_WS0010_GRAPHICS_MAX_RAM_GROWTH=16
