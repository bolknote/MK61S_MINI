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
  -DARDUINO_BLACKPILL_F401CC \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$root/code" \
  "$root/tests/program_store_self_test.cpp" \
  "$root/code/loadable_module_system_app.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/program_store.cpp" \
  "$root/code/storage_geometry.cpp" \
  "$root/code/storage_path.cpp" \
  "$root/code/shared_scratch.cpp" \
  "$root/code/zx0.cpp" \
  -o "$out"

"$out"
