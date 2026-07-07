#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

clang++ -std=c++17 -Wall -Wextra -Werror \
  tests/virtual_fat_self_test.cpp \
  code/shared_scratch.cpp \
  -o /tmp/virtual_fat_self_test

/tmp/virtual_fat_self_test
