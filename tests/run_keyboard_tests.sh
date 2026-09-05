#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
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

if rg -n 'exclude_before|drop_pending_key_events|drop_menu_exit_key_events|drop_key_events_until_release' "$root/code"; then
  printf 'Legacy input discard path must not coexist with keyboard handoff.\n' >&2
  exit 1
fi
