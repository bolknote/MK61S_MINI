#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-language-vm.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$root/code" "$root/tests/language_vm_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" \
  -o "$work/test"
"$work/test"
for variant in compact f64; do
  extra=()
  if [[ "$variant" == "f64" ]]; then extra=(-DLANGUAGE_VM_TEST_NO_DECIMAL_RECIPE); fi
  clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" "${extra[@]}" \
    -I"$root/code" "$root/tests/language_vm_input_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" \
    "$root/code/language_vm_validation.cpp" -o "$work/input-$variant"
  "$work/input-$variant"
done
MK61_LANGUAGE_VM_TEST=1 bash "$root/tests/run_tinybasic_tests.sh"
MK61_LANGUAGE_VM_TEST=1 bash "$root/tests/run_focal_tests.sh"
