#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-review.XXXXXX")"
trap 'rm -rf "$work"' EXIT
for backend in 0 1; do
  for kind in HOST MK61_BUILD_LANGUAGE_VM_MODULE LANGUAGE_VM_TEST_PICO_ENTRY; do
    clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
      -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
      -DMK61_MATH_BACKEND="$backend" -D"$kind" -I"$root/code" \
      "$root/tests/language_vm_review_self_test.cpp" \
      "$root/code/language_vm_flow.cpp" "$root/code/language_compiler_flow.cpp" \
      "$root/code/language_vm_validation.cpp" "$root/code/language_vm.cpp" \
      "$root/code/language_bytecode.cpp" -o "$work/review"
    "$work/review"
  done
done
