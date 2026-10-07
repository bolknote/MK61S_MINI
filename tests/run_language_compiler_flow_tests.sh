#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-compiler-flow.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=(-Wall -Wextra -Werror)
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 "${flags[@]}" -I"$root/code" \
  "$root/tests/language_compiler_flow_self_test.cpp" \
  "$root/code/language_compiler_flow.cpp" -o "$work/test"
"$work/test"
