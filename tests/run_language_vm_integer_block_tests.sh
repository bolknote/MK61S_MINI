#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-integer-block.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in 0 1; do
for block in 0 1; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_VM_INTEGER_BLOCK="$block" -DMK61_MATH_BACKEND="$backend" \
    -DLANGUAGE_VM_TEST_INTEGER_BLOCK \
    -I"$root/code" "$root/tests/language_vm_integer_block_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/block-$block"
  "$work/block-$block" > "$work/block-$block.txt"
done
cmp "$work/block-0.txt" "$work/block-1.txt"
cat "$work/block-1.txt"
done
