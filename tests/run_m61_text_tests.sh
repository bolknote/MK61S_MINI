#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_m61_text_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for cache_bytes in 64 1024; do
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DM61_TEXT_HOST_TEST -DMK61_M61_READ_CACHE_BYTES="$cache_bytes" \
  -I"$root/code" \
  "$root/tests/m61_text_self_test.cpp" \
  "$root/code/m61_text.cpp" \
  "$root/code/zx0_stream.cpp" "$root/code/program_load.cpp" \
  -o "$out"

"$out"
done
python3 "$root/tests/m61_controls_self_test.py"
python3 "$root/tests/game_manual_bind_self_test.py"
