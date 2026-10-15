#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-compiled-block.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in 0 1; do
for configuration in 0 1 2 3; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_MATH_BACKEND="$backend" -DMK61_VM_INTEGER_BLOCK="$((configuration & 1))" \
    -DMK61_VM_COMPARE_BLOCK="$(((configuration >> 1) & 1))" -DLANGUAGE_VM_TRACE \
    -DLANGUAGE_VM_TEST_INTEGER_BLOCK -DLANGUAGE_VM_TEST_COMPARE_BLOCK \
    -I"$root/code" "$root/tests/language_vm_compiled_block_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/blocks-$backend"
  "$work/blocks-$backend"
done
done
