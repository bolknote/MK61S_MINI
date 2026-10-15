#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-zx0-encode.XXXXXX")"
trap 'rm -rf "$work"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for variant in scalar word; do
  kernel_flags=()
  if [[ "$variant" == word ]]; then kernel_flags=(-DMK61_ZX0_WORD_TEST=1); fi
  clang++ -std=c++17 -O2 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" "${kernel_flags[@]}" \
    -I"$root/code" \
    "$root/tests/zx0_encode_self_test.cpp" \
    "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    -o "$work/$variant"
  "$work/$variant"
done
