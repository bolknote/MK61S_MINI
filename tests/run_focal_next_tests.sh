#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-focal-next.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ ${MK61_TEST_SANITIZERS:-0} == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
if [[ ${MK61_VM_DSP_SCAN_TEST:-0} == 1 ]]; then flags+=(-DLANGUAGE_VM_TEST_DSP_SCAN); fi
for profile in MINI CLASSIC 40TH; do
 clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" -DFOCAL_HOST_TEST -DMK61_KEYBOARD_$profile \
  -I"$root/code" "$root/tests/focal_next_self_test.cpp" "$root/code/focal.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/focal-$profile"
 "$work/focal-$profile"
done
clang++ -std=c++17 -Wall -Wextra -Werror -DFOCAL_HOST_TEST -DMK61_ENABLE_FOCAL=0 -I"$root/code" \
 -c "$root/code/focal.cpp" -o "$work/disabled.o"
