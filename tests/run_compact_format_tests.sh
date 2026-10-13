#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_compact_format_self_test"
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
"${CXX:-c++}" -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" "$root/tests/compact_format_self_test.cpp" "$root/code/compact_format.cpp" -o "$out"
"$out"
