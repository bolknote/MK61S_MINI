#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_race_core_runner"
python3 "$root/tools/race/build.py" --check
for profile in native mini; do
  target="$out"
  profile_flags=(-DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=1 -DMK61_DISPLAY_UC1609)
  if [[ "$profile" == mini ]]; then
    target="$out-mini"
    profile_flags=(-DMK61_CORE_NATIVE_HOT_PATHS=0 -DMK61_CORE_PACKED_AMK=0 -DMK61_LCD1602_A00)
  fi
  "${MK61_HOST_CXX:-clang++}" -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
    -DMK61_MATH_BACKEND=1 -DMK61_CORE_HOT_TABLES_IN_SRAM=0 \
    "${profile_flags[@]}" -DM61_TEXT_HOST_TEST \
    -include "$root/tests/mk_math_shim/debug.h" -I"$root/tests/mk_math_shim" -I"$root/code" \
    "$root/tests/race_core_runner.cpp" "$root/tests/elite_loader_host.cpp" \
    "$root/code/m61_text.cpp" "$root/code/mk_math_core.cpp" "$root/code/mk61emu_core.cpp" \
    "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" \
    "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" "$root/code/zx0_stream.cpp" \
    "$root/code/program_load.cpp" -o "$target"
  python3 "$root/tests/race_game_test.py" "$target"
done
