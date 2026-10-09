#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-source-scan.XXXXXX")"
trap 'rm -rf "$work"' EXIT
for variant in scalar dsp-emulated; do
  extra=()
  if [[ "$variant" == dsp-emulated ]]; then extra=(-DLANGUAGE_VM_TEST_DSP_SCAN); fi
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-omit-frame-pointer "${extra[@]}" \
    -I"$root/code" "$root/tests/language_source_scan_self_test.cpp" -o "$work/$variant"
  "$work/$variant"
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-omit-frame-pointer "${extra[@]}" \
    -I"$root/code" "$root/tests/language_source_scan_compiler_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/compiler-$variant"
  "$work/compiler-$variant"
done
