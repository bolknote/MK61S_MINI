#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

build_and_run() {
  local profile="$1"
  local define="${2:-}"
  local out="${TMPDIR:-/tmp}/mk61_keyboard_layout_${profile}_self_test"
  local profile_flags=()
  if [[ -n "$define" ]]; then
    profile_flags+=("-D${define}")
  fi

  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    "${profile_flags[@]}" \
    -I"$root/tests/mk_math_shim" \
    -I"$root/code" \
    "$root/tests/keyboard_layout_profile_self_test.cpp" \
    -o "$out"

  "$out"
}

build_and_run mini MK61_KEYBOARD_MINI
build_and_run classic MK61_KEYBOARD_CLASSIC
build_and_run 40th MK61_KEYBOARD_40TH
