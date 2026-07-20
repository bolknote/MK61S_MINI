#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_ledcontrol_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

build_and_run() {
  local profile="$1"
  local inactive_level="$2"
  shift 2
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    -I"$root/tests/ledcontrol_shim" \
    -I"$root/code" \
    -DMK61_LED_EXPECT_INACTIVE_LEVEL="$inactive_level" \
    "$@" \
    "$root/tests/ledcontrol_self_test.cpp" \
    "$root/code/ledcontrol.cpp" \
    -o "$out-$profile"
  "$out-$profile"
}

build_and_run mini-v2 0 -DREVISION_V2
build_and_run mini-v3 0 -DREVISION_V3
build_and_run classic-v2 1 -DMK61_BOARD_CLASSIC_V2
build_and_run classic-v3 0 -DMK61_BOARD_CLASSIC_V3
build_and_run 40th 1 -DMK61_BOARD_40TH
