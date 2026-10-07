#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-math-helpers.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]];then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer);fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" \
  "$root/tests/math_helpers_self_test.cpp" -o "$work/test"
"$work/test"
