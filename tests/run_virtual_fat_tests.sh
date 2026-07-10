#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  tests/virtual_fat_self_test.cpp \
  code/language_workspace.cpp \
  code/shared_scratch.cpp \
  -o /tmp/virtual_fat_self_test

/tmp/virtual_fat_self_test
