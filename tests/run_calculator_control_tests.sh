#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-control-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
  "${sanitizer_flags[@]}" \
  -DMK61_MATH_BACKEND=1 -DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=1 \
  -DMK61_CORE_HOT_TABLES_IN_SRAM=0 -DMK61_DISPLAY_UC1609 -DMK61_KEYBOARD_CLASSIC=1 \
  -include "$root/tests/mk_math_shim/debug.h" \
  -I"$root/tests/mk_math_shim" -I"$root/code" \
  "$root/tests/calculator_control_native_self_test.cpp" "$root/code/calculator_control.cpp" \
  "$root/code/mk61emu_core.cpp" "$root/code/mk_math_core.cpp" \
  "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" \
  "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
  -o "$build_dir/test"
"$build_dir/test"
