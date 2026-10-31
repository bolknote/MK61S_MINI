#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-native-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for amk_bits in 8 6; do
for amk_words in 0 1; do
  if [[ "$amk_bits" == 8 && "$amk_words" == 1 ]]; then continue; fi
for dcw_fields in 0 1; do
for core_case in 0:0 0:2 1:0 1:2 1:1; do
  shared=${core_case%:*}
  hot_tables=${core_case#*:}
  if [[ "$hot_tables" == 1 && "$amk_bits" != 6 ]]; then continue; fi
  # The new storage format uses the already checked F401 shared/field path.
  if [[ "$amk_bits" == 6 && ( "$dcw_fields" != 1 || "$shared" != 1 ) ]]; then continue; fi
  amk_flags=()
  if [[ "$amk_bits" == 6 ]]; then amk_flags=(-DMK61_TEST_AND_AMK_6BIT=1); fi
  if [[ "$amk_words" == 1 ]]; then amk_flags+=(-DMK61_MEMORY_TEST_WORDS=1); fi
  sharing_flags=()
  if [[ "$shared" == 1 ]]; then sharing_flags=(-DMK61_TEST_SHARED_TICK=1); fi
  dcw_flags=()
  if [[ "$dcw_fields" == 1 ]]; then
    dcw_flags=(-DMK61_TEST_DCW_FIELDS=1 -DMK61_CORE_PREDECODED_ROM=0)
  fi
  echo "Native boundary verification: AMK bits=$amk_bits word reads=$amk_words dcw fields=$dcw_fields shared=$shared hot tables=$hot_tables"
  # core_native_self_test includes the real core.cpp to access private ticks;
  # do not link a second copy. Keep the scalar decoder independent of packed AMK.
  clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
    "${sanitizer_flags[@]}" \
    "${sharing_flags[@]}" "${dcw_flags[@]}" "${amk_flags[@]}" \
    -DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=0 \
    -DMK61_CORE_HOT_TABLES_IN_SRAM="$hot_tables" -DMK61_DISPLAY_UC1609 \
    -include "$root/tests/mk_math_shim/debug.h" \
    -I"$root/tests/mk_math_shim" -I"$root/code" \
    "$root/tests/core_native_self_test.cpp" \
    "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" \
    "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    -o "$build_dir/core-native-$amk_bits-$amk_words-$dcw_fields-$shared-$hot_tables"
  "$build_dir/core-native-$amk_bits-$amk_words-$dcw_fields-$shared-$hot_tables"
done
done
done
done
