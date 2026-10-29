#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${MK61_RUNNER_BUILD_DIR:-}" ]]; then
  build_dir="$MK61_RUNNER_BUILD_DIR"
  mkdir -p "$build_dir"
else
  build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-runner.XXXXXX")"
  trap 'rm -rf "$build_dir"' EXIT
fi
python3 "$root/tools/runner/build.py" --check
sanitizers=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  sanitizers=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for profile in native mini; do
  profile_flags=(-DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=1 -DMK61_DISPLAY_UC1609 -DMK61_M61_READ_CACHE_BYTES=1024)
  if [[ "$profile" == mini ]]; then
    profile_flags=(-DMK61_CORE_NATIVE_HOT_PATHS=0 -DMK61_CORE_PACKED_AMK=0 -DMK61_LCD1602_A00)
  fi
  "${MK61_HOST_CXX:-clang++}" -std=c++17 -O2 -fconstexpr-steps=10000000 \
    "${sanitizers[@]}" -DMK61_CORE_STANDALONE=1 -DMK61_MATH_BACKEND=1 "${profile_flags[@]}" \
    -include "$root/tests/mk_math_shim/debug.h" -I"$root/tests/mk_math_shim" -I"$root/code" \
    -c "$root/code/terminal_script_runtime.cpp" -o "$build_dir/terminal-$profile.o"
  "${MK61_HOST_CXX:-clang++}" -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
    -fconstexpr-steps=10000000 "${sanitizers[@]}" -DM61_TEXT_HOST_TEST \
    -DMK61_MATH_BACKEND=1 -DMK61_CORE_HOT_TABLES_IN_SRAM=0 "${profile_flags[@]}" \
    -include "$root/tests/mk_math_shim/debug.h" -I"$root/tests/mk_math_shim" -I"$root/code" \
    "$root/tests/runner_core_runner.cpp" "$build_dir/terminal-$profile.o" \
    "$root/code/terminal_catalog.cpp" "$root/code/terminal_key_sequence.cpp" \
    "$root/code/m61_text.cpp" "$root/code/mk_math_core.cpp" "$root/code/mk61emu_core.cpp" \
    "$root/code/language_workspace.cpp" "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" \
    "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" "$root/code/zx0_stream.cpp" \
    "$root/code/program_load.cpp" -o "$build_dir/runner-$profile"
  python3 "$root/tests/runner_game_test.py" "$build_dir/runner-$profile"
  python3 "$root/tests/m61_timer_runtime_test.py" "$build_dir/runner-$profile"
done
