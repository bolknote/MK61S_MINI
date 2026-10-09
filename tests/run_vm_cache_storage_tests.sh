#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-storage.XXXXXX")"
trap 'rm -rf "$work"' EXIT HUP INT TERM
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  "$root/tests/experimental/vm_cache_lzss_self_test.cpp" -o "$work/codec"
"$work/codec"
python3 "$root/tests/vm_cache_storage_self_test.py"
python3 "$root/tests/vm_cache_replay_self_test.py"
