#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_compact_math_self_test"
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for compact in 0 1; do
  clang++ -std=c++17 -O2 -Wall -Wextra -Werror -ffp-contract=off \
    "${flags[@]}" -DMK61_MATH_BACKEND=0 -DMK61_USE_COMPACT_LIBM="$compact" \
    -I"$root/code" "$root/tests/compact_math_self_test.cpp" \
    "$root/code/compact_math.cpp" -o "$out"
  "$out" "${MK61_MATH_SAMPLES:-100000}" "$root/tests/fixtures/compact_math_binary64.tsv"
done
