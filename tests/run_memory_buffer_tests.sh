#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

build_and_run() {
  local name="$1"
  local expected_size="$2"
  shift 2
  local out="${TMPDIR:-/tmp}/memory_buffers_self_test_$name"
  clang++ -std=c++17 -Wall -Wextra -Werror \
    -DMK61_ENABLE_FOCAL=0 \
    -DMK61_ENABLE_TINYBASIC=0 \
    -DMK61_EXPECTED_EXCLUSIVE_BUFFER_SIZE="$expected_size" \
    "$@" \
    "${sanitizer_flags[@]}" \
    "$root/tests/memory_buffers_self_test.cpp" \
    "$root/code/exclusive_buffer.cpp" \
    "$root/code/language_workspace.cpp" \
    "$root/code/shared_scratch.cpp" \
    -o "$out"
  "$out"
}

build_and_run host 8192 -DMK61_DISPLAY_UC1609
# Проверяет и компактный размер, и то, что полный профиль платы включает
# буфер в отдельной translation unit без предварительного include config.h.
build_and_run f401 1536 -DSTM32F401xC -DMK61_BOARD_CLASSIC_V3
