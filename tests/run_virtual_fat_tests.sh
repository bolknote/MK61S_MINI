#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$root/code" \
  "$root/tests/virtual_fat_self_test.cpp" \
  "$root/code/virtual_fat.cpp" \
  "$root/code/program_store.cpp" \
  "$root/code/storage_geometry.cpp" \
  "$root/code/language_workspace.cpp" \
  "$root/code/shared_scratch.cpp" \
  -o /tmp/virtual_fat_self_test

/tmp/virtual_fat_self_test
