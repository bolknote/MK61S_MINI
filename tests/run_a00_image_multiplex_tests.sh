#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="${TMPDIR:-/tmp}/mk61-a00-image-multiplex-tests"
mkdir -p "$build_dir"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

c++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/code/a00_image_multiplex.cpp" \
  "$root/tests/a00_image_multiplex_self_test.cpp" \
  -o "$build_dir/a00_image_multiplex_self_test"

"$build_dir/a00_image_multiplex_self_test"
