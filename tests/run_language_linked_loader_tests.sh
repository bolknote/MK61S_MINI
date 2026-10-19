#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-linked-loader.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in 0 1; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_MATH_BACKEND="$backend" -DMK61_LINKED_VM_POC=1 -DMK61_BUILD_VM_FILE_CACHE_MODULE \
    -I"$root/code" -I"$root/tools" \
    "$root/tests/language_linked_loader_self_test.cpp" "$root/code/language_linked_loader.cpp" \
    "$root/code/language_linked_program.cpp" "$root/code/language_bytecode.cpp" \
    "$root/code/language_vm.cpp" -o "$work/test-$backend"
  "$work/test-$backend"
done
