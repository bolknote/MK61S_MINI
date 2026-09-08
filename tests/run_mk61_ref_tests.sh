#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_ref_self_test"
portable_out="${TMPDIR:-/tmp}/mk61_ref_portable_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/mk61_ref_self_test.cpp" \
  -o "$out"

"$out"

# Компилирует отдельную условную ветку System APP. Обычная прошивка и основной
# host-test её не видят, поэтому без этого теста несовместимый const void* мог
# обнаружиться только при поздней сборке переносимых FOCAL/BASIC на GitHub.
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/mk61_ref_portable_self_test.cpp" \
  -o "$portable_out"

"$portable_out"
