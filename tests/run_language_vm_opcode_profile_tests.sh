#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-opcode-profile.XXXXXX")"
trap 'rm -rf "$work"' EXIT
sanitizers=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  sanitizers=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in 0 1; do
for timing in 0 1; do
for integers in 0 1; do
for block in 0 1; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${sanitizers[@]}" \
    -DMK61_VM_INTEGER_BLOCK="$block" -DMK61_MATH_BACKEND="$backend" \
    -DMK61_VM_OPCODE_PROFILE_TIMING="$timing" -DMK61_VM_OPCODE_PROFILE_INTEGER_COUNTS="$integers" \
    -DMK61_VM_OPCODE_PROFILE=1 -DLANGUAGE_VM_OPCODE_PROFILE_TEST -DLANGUAGE_VM_TEST_INTEGER_BLOCK \
    -include "$root/tests/stubs/vm_opcode_profile.hpp" -I"$root/code" \
    "$root/tests/language_vm_opcode_profile_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/profile-$block"
  "$work/profile-$block"
done
done
done
done
