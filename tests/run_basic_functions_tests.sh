#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-basic-functions.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ ${MK61_TEST_SANITIZERS:-0} == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
if [[ ${MK61_VM_DSP_SCAN_TEST:-0} == 1 ]]; then flags+=(-DLANGUAGE_VM_TEST_DSP_SCAN); fi
failures=0
for variant in native vm; do
 for profile in MINI CLASSIC 40TH; do
 extra=(); if [[ $variant == vm ]]; then extra=(-DMK61_LANGUAGE_VM_TEST); fi
 clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" "${extra[@]}" -DTINYBASIC_HOST_TEST -DTINYBASIC_SELF_TEST -DMK61_KEYBOARD_$profile \
  -I"$root/code" "$root/tests/basic_functions_self_test.cpp" "$root/code/tinybasic.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/$variant"
 "$work/$variant" || failures=$((failures+1))
 done
done
[[ $failures == 0 ]]
