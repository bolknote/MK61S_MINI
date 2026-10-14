#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_native_eabi_self_test"
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
  -DMK61_USE_NATIVE_EABI=1 -I"$root/code" \
  "$root/tests/native_eabi_self_test.cpp" "$root/code/native_eabi.cpp" -o "$out"
"$out" "${MK61_EABI_SAMPLES:-1000000}"
