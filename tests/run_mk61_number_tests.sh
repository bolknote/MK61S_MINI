#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-number-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi

for backend in 0 1; do
  # The fixture includes the real core.cpp for actual ring-layout/formatter
  # coverage; do not link a second copy or substitute calculator I/O stubs.
  clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
    "${sanitizer_flags[@]}" \
    -DMK61_MATH_BACKEND="$backend" -DMK61_CORE_NATIVE_HOT_PATHS=1 \
    -DMK61_CORE_PACKED_AMK=0 -DMK61_CORE_HOT_TABLES_IN_SRAM=0 -DMK61_DISPLAY_UC1609 \
    -include "$root/tests/mk_math_shim/debug.h" \
    -I"$root/tests/mk_math_shim" -I"$root/code" \
    "$root/tests/mk61_number_self_test.cpp" \
    "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" \
    "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    -o "$build_dir/mk61-number-$backend"
  "$build_dir/mk61-number-$backend"
done

python3 "$root/tests/terminal_if_number_self_test.py"
