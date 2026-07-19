#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_program_store_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$root/code" \
  "$root/tests/program_store_self_test.cpp" \
  "$root/code/program_store.cpp" \
  "$root/code/storage_geometry.cpp" \
  "$root/code/storage_path.cpp" \
  "$root/code/shared_scratch.cpp" \
  -o "$out"

"$out"
