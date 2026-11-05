#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-language-compact.XXXXXX")"
trap 'rm -rf "$work"' EXIT
for backend in 0 1; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -DMK61_MATH_BACKEND="$backend" -I"$root/code" \
    "$root/tests/language_compact_self_test.cpp" -o "$work/test"
  "$work/test"
done
