#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-cache-capacity.XXXXXX")"
trap 'rm -rf "$work"' EXIT
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -I"$root/code" \
  "$root/tests/language_vm_cache_capacity_self_test.cpp" -o "$work/capacity"
"$work/capacity"
for bytes in 24576 32768; do
  MK61_VM_CACHE_BYTES_TEST="$bytes" MK61_TEST_SANITIZERS=1 \
    bash "$root/tests/run_language_vm_image_cache_tests.sh"
  MK61_VM_CACHE_BYTES_TEST="$bytes" MK61_TEST_SANITIZERS=1 \
    bash "$root/tests/run_language_vm_file_cache_tests.sh"
done
bash "$root/tests/run_language_vm_mixed_cache_tests.sh"
MK61_VM_CACHE_MIXED_TEST=1 MK61_TEST_SANITIZERS=1 \
  bash "$root/tests/run_language_vm_file_cache_tests.sh"
python3 "$root/tests/hil_vm_compiled_blocks_self_test.py"
