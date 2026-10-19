#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-linked-program.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in 0 1; do
for kind in HOST MK61_BUILD_LANGUAGE_VM_MODULE; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_MATH_BACKEND="$backend" -D"$kind" \
    -I"$root/code" -I"$root/tests" "$root/tests/language_linked_program_self_test.cpp" \
    "$root/code/language_linked_program.cpp" "$root/code/language_bytecode.cpp" \
    "$root/code/language_vm.cpp" -o "$work/test-$backend"
  "$work/test-$backend"
done
done
