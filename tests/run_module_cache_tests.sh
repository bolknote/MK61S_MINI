#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-module-cache.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]];then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer);fi
python3 "$root/tests/module_cache_surface.py" "$work/module_cache.inc"
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" -I"$work" \
  "$root/tests/module_cache_self_test.cpp" -o "$work/test"
"$work/test"
