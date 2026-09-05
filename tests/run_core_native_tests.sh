#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-native-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for hot_tables in 0 2; do
  echo "Native boundary verification: hot tables=$hot_tables"
  # core_native_self_test includes the real core.cpp to access private ticks;
  # do not link a second copy. Keep the scalar decoder independent of packed AMK.
  clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
    "${sanitizer_flags[@]}" \
    -DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=0 \
    -DMK61_CORE_HOT_TABLES_IN_SRAM="$hot_tables" -DMK61_DISPLAY_UC1609 \
    -include "$root/tests/mk_math_shim/debug.h" \
    -I"$root/tests/mk_math_shim" -I"$root/code" \
    "$root/tests/core_native_self_test.cpp" \
    "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" \
    "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    -o "$build_dir/core-native-$hot_tables"
  "$build_dir/core-native-$hot_tables"
done
