#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-segment-lcd1602.XXXXXX")"
trap 'rm -f "$test_dir/a00" "$test_dir/a02"; rmdir "$test_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for profile in a00 a02; do
  flags=(-DMK61_LCD1602_A00)
  if [[ "$profile" == a02 ]]; then flags=(-DMK61_LCD1602_A02); fi
  clang++ -std=c++17 -Wall -Wextra -Werror -pedantic \
    "${sanitizer_flags[@]}" -DARDUINO=100 "${flags[@]}" \
    -I"$root/code" -I"$root/tests/mk_math_shim" \
    "$root/tests/segment_lcd1602_self_test.cpp" -o "$test_dir/$profile"
  "$test_dir/$profile"
done
