#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-eliza-tests.XXXXXX")"
trap 'rm -rf "$work"' EXIT

python3 "$root/tools/generate_eliza_doctor.py" --check

flags=(-std=c11 -O2 -Wall -Wextra -Werror
  -I"$root/examples/portable-apps/ELIZA")
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang "${flags[@]}" \
  "$root/tests/eliza_engine_self_test.c" \
  "$root/examples/portable-apps/ELIZA/eliza_engine.c" \
  -o "$work/eliza-engine"
"$work/eliza-engine"

clang "${flags[@]}" -c \
  "$root/examples/portable-apps/ELIZA/eliza_engine.c" \
  -o "$work/eliza-engine.o"

ui_flags=(-std=c++17 -O2 -Wall -Wextra -Werror -Wno-missing-field-initializers)
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  ui_flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ "${ui_flags[@]}" \
  -I"$root/code" -I"$root/sdk/portable/include" \
  -I"$root/examples/portable-apps/ELIZA" \
  "$root/tests/eliza_app_ui_self_test.cpp" \
  "$work/eliza-engine.o" \
  -o "$work/eliza-ui"
"$work/eliza-ui"
