#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_elite_core_runner"
python3 "$root/tools/elite/build.py" --check
clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
  -DMK61_MATH_BACKEND=1 -DMK61_CORE_HOT_TABLES_IN_SRAM=0 \
  -DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=1 -DMK61_DISPLAY_UC1609 -DM61_TEXT_HOST_TEST \
  -include "$root/tests/mk_math_shim/debug.h" -I"$root/tests/mk_math_shim" -I"$root/code" \
  "$root/tests/elite_core_runner.cpp" "$root/tests/elite_loader_host.cpp" \
  "$root/code/m61_text.cpp" "$root/code/mk_math_core.cpp" \
  "$root/code/mk61emu_core.cpp" "$root/code/language_workspace.cpp" \
  "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" -o "$out"
python3 "$root/tests/elite_game_test.py" "$out"
