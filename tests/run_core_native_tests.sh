#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-native-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for dcw_fields in 0 1; do
for core_case in 0:0 0:2 1:0 1:2; do
  shared=${core_case%:*}
  hot_tables=${core_case#*:}
  sharing_flags=()
  if [[ "$shared" == 1 ]]; then sharing_flags=(-DMK61_TEST_SHARED_TICK=1); fi
  dcw_flags=()
  if [[ "$dcw_fields" == 1 ]]; then
    dcw_flags=(-DMK61_TEST_DCW_FIELDS=1 -DMK61_CORE_PREDECODED_ROM=0)
  fi
  echo "Native boundary verification: dcw fields=$dcw_fields shared=$shared hot tables=$hot_tables"
  # core_native_self_test includes the real core.cpp to access private ticks;
  # do not link a second copy. Keep the scalar decoder independent of packed AMK.
  clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
    "${sanitizer_flags[@]}" \
    "${sharing_flags[@]}" "${dcw_flags[@]}" \
    -DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=0 \
    -DMK61_CORE_HOT_TABLES_IN_SRAM="$hot_tables" -DMK61_DISPLAY_UC1609 \
    -include "$root/tests/mk_math_shim/debug.h" \
    -I"$root/tests/mk_math_shim" -I"$root/code" \
    "$root/tests/core_native_self_test.cpp" \
    "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" \
    "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    -o "$build_dir/core-native-$dcw_fields-$shared-$hot_tables"
  "$build_dir/core-native-$dcw_fields-$shared-$hot_tables"
done
done
