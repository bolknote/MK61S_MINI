#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
repeat_work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-repeat.XXXXXX")"
trap 'rm -rf "$repeat_work"' EXIT
for math in 0 1; do
for reader in HOST MK61_BUILD_LANGUAGE_VM_MODULE; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -DMK61_MATH_BACKEND="$math" -D"$reader" -I"$root/code" -I"$root/tests" \
    "$root/tests/language_vm_repeat_self_test.cpp" "$root/code/language_bytecode.cpp" \
    "$root/code/language_vm.cpp" "$root/code/language_vm_flow.cpp" \
    "$root/code/language_vm_validation.cpp" "$root/code/language_compiler_flow.cpp" \
    "$root/code/app_flow.cpp" -o "$repeat_work/test"
  "$repeat_work/test"
done
done
