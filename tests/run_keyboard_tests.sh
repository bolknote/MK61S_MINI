#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/tests/keyboard_source_gate_self_test.py"
bash "$root/tests/check_keyboard_handoff.sh" "$root/code"

out="${TMPDIR:-/tmp}/mk61_keyboard_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/keyboard_self_test.cpp" \
  -o "$out"

"$out"

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" -I"$root/code" \
  "$root/tests/keyboard_handoff_self_test.cpp" -o "${out}_handoff"
"${out}_handoff"
