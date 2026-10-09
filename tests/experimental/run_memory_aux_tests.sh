#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-memory-aux.XXXXXX")"
trap 'rm -rf "$work"' EXIT
clang++ -std=c++17 -O3 -Wall -Wextra -Werror -fno-builtin \
  -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
  -I"$root/code" "$root/tests/experimental/memory_aux_self_test.cpp" -o "$work/test"
"$work/test"
