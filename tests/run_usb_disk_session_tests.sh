#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/usb_disk_session_self_test"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/tests/usb_disk_session_self_test.cpp" \
  -o "$out"

"$out" \
  "$root/tests/data/vfat_transcripts/sync-success.vfat" \
  "$root/tests/data/vfat_transcripts/reject-repair-retry.vfat" \
  "$root/tests/data/vfat_transcripts/io-failure-disconnect.vfat" \
  "$root/tests/data/vfat_transcripts/reset-dirty.vfat"
