#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  -DMK61_ENABLE_FOCAL=0 \
  -DMK61_ENABLE_TINYBASIC=0 \
  -DMK61_DISPLAY_UC1609 \
  "${sanitizer_flags[@]}" \
  "$root/tests/memory_buffers_self_test.cpp" \
  "$root/code/exclusive_buffer.cpp" \
  "$root/code/language_workspace.cpp" \
  "$root/code/shared_scratch.cpp" \
  -o /tmp/memory_buffers_self_test

/tmp/memory_buffers_self_test
