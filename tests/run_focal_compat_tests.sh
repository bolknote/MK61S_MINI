#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-focal-compat.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ ${MK61_TEST_SANITIZERS:-0} == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
failures=0
if [[ ${MK61_VM_DSP_SCAN_TEST:-0} == 1 ]]; then flags+=(-DLANGUAGE_VM_TEST_DSP_SCAN); fi
for profile in MINI CLASSIC 40TH; do
 for trace in 0 1; do
  extra=();if [[ $trace == 1 ]]; then extra=(-DMK61_FOCAL_TRACE=1); fi
  clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" "${extra[@]}" -DFOCAL_HOST_TEST -DMK61_KEYBOARD_$profile \
   -I"$root/code" "$root/tests/focal_compat_self_test.cpp" \
   "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/compat-$profile-$trace"
  "$work/compat-$profile-$trace" || failures=$((failures+1))
 done
done

[[ $failures == 0 ]]
