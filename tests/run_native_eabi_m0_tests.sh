#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-m0-eabi.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
    flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -ffp-contract=off "${flags[@]}" \
    -DMK61_USE_M0_EABI=1 -I"$root/code" "$root/code/native_eabi_m0.cpp" \
    "$root/tests/native_eabi_m0_self_test.cpp" -o "$build/self-test"
"$build/self-test" "${MK61_EABI_SAMPLES:-100000}"
