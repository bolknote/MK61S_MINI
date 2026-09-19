#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
sanitizer_flags=()
body_profile="${MK61_CORE_BODY_PROFILE:-0}"
# Exercise the F411 path in ordinary CI. The differential test compiled into
# this build also runs the generic decoder from every saved start state.
native_hot_paths="${MK61_CORE_NATIVE_HOT_PATHS:-1}"
packed_amk="${MK61_CORE_PACKED_AMK:-1}"
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

build_and_run() {
  local name="$1"
  local hot_tables="$2"
  local out="${TMPDIR:-/tmp}/mk61_mk_math_self_test_$name"

  # Собираем подсистему CORE вместе с настоящим ядром МК-61 на хосте.
  # Заголовки-заглушки (Arduino.h/debug.h) идут первыми в пути включения, чтобы
  # зависимости только для прошивки разрешались в хостовые заглушки.
  clang++ -std=c++17 -Wall -Wextra -Wno-unused -Wno-unused-parameter \
    -Wno-cpp \
    "${sanitizer_flags[@]}" \
    -DMK61_MATH_BACKEND=1 \
    -DMK61_CORE_HOT_TABLES_IN_SRAM="$hot_tables" \
    -DMK61_CORE_BODY_PROFILE="$body_profile" \
    -DMK61_CORE_NATIVE_HOT_PATHS="$native_hot_paths" \
    -DMK61_CORE_PACKED_AMK="$packed_amk" \
    -DMK61_DISPLAY_UC1609 \
    -include "$root/tests/mk_math_shim/debug.h" \
    -I"$root/tests/mk_math_shim" \
    -I"$root/code" \
    "$root/tests/mk_math_self_test.cpp" \
    "$root/code/mk_math_core.cpp" \
    "$root/code/mk61emu_core.cpp" \
    "$root/code/language_workspace.cpp" \
    "$root/code/shared_memory.cpp" \
    "$root/code/workspace_swap.cpp" \
    "$root/code/zx0.cpp" \
    "$root/code/zx0_encode.cpp" \
    -o "$out"

  "$out"
}

build_and_run flash 0
build_and_run evictable-sram 2
