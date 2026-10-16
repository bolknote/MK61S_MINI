#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_m61_text_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for cache_case in 64:0 256:1 1023:1 1024:1 1024:0; do
cache_bytes=${cache_case%:*}
prepared=${cache_case#*:}
for scoped in 0 1; do
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DM61_TEXT_HOST_TEST -DMK61_M61_READ_CACHE_BYTES="$cache_bytes" \
  -DMK61_M61_PREPARED_CACHE="$prepared" \
  -DMK61_SCOPED_RESIDENT_BUFFERS="$scoped" \
  -I"$root/tests/mk_math_shim" -I"$root/code" \
  "$root/tests/m61_text_self_test.cpp" \
  "$root/code/m61_text.cpp" \
  "$root/code/terminal_catalog.cpp" \
  "$root/code/zx0_stream.cpp" "$root/code/program_load.cpp" \
  "$root/code/shared_memory.cpp" \
  -o "$out"

"$out"
done
done
python3 "$root/tests/m61_controls_self_test.py"
python3 "$root/tests/game_manual_bind_self_test.py"
