#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-qbench.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
# The scalar ROM decoder provides an independent check of the optimized host core.
clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
  -DMK61_MATH_BACKEND=1 -DMK61_CORE_NATIVE_HOT_PATHS=0 \
  -DMK61_CORE_PREDECODED_ROM=0 -DMK61_CORE_PACKED_AMK=0 \
  -DMK61_CORE_HOT_TABLES_IN_SRAM=0 -DMK61_DISPLAY_UC1609 \
  -include "$root/tests/mk_math_shim/debug.h" \
  -I"$root/tests/mk_math_shim" -I"$root/code" \
  "$root/tests/queens_benchmark_runner.cpp" "$root/code/mk61emu_core.cpp" \
  "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" \
  "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
  -o "$build_dir/runner"
python3 "$root/tests/queens_benchmark_self_test.py" "$build_dir/runner"
