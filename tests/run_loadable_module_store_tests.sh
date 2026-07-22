#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_loadable_module_store_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/loadable_module_store_self_test.cpp" \
  "$root/code/loadable_module_store.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/zx0.cpp" \
  "$root/code/storage_geometry.cpp" \
  -o "$out"

"$out"
