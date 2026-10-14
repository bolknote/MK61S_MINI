#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-buffer-scan.XXXXXX")"
trap 'rm -rf "$work"' EXIT
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I"$root/code" -I"$root/tests/experimental" \
  "$root/tests/experimental/buffer_scan_self_test.cpp" \
  "$root/code/usb_screen_protocol.cpp" -o "$work/check"
"$work/check"
