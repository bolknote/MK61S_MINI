#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_chip8_self_test"
echo8_out="${TMPDIR:-/tmp}/mk61_echo8_rebuilt.ch8"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/chip8_self_test.cpp" \
  "$root/code/chip8.cpp" \
  -o "$out"

python3 "$root/tools/chip8_assemble.py" \
  "$root/games/echo8.asm" "$echo8_out" >/dev/null
cmp "$echo8_out" "$root/games/echo8.ch8"

"$out" "$root/games/br8kout.ch8" "$root/games/fuse.ch8" \
  "$root/games/space-invaders.ch8" "$root/games/echo8.ch8"
