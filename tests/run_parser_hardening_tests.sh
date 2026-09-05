#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mktemp -d "${TMPDIR:-/tmp}/mk61-parser-hardening.XXXXXX")"
trap 'rm -rf "$out"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" \
  "$root/tests/parser_hardening_self_test.cpp" "$root/code/zx0.cpp" \
  "$root/code/zx0_encode.cpp" "$root/code/loadable_module_format.cpp" \
  -o "$out/parser-hardening"
"$out/parser-hardening"
