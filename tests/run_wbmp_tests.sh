#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

build_and_run() {
  local variant="$1"
  shift
  local out="${TMPDIR:-/tmp}/mk61_wbmp_self_test_${variant}"

  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    "$@" \
    -I"$root/code" \
    "$root/code/wbmp.cpp" \
    "$root/tests/wbmp_self_test.cpp" \
    -o "$out"

  "$out"
}

build_and_run generic
build_and_run bit_band -D__ARM_ARCH_7EM__ -DSTM32F411xE

reader_out="${TMPDIR:-/tmp}/mk61_wbmp_reader_self_test"
clang++ -std=c++17 -Wall -Wextra -Werror "${sanitizer_flags[@]}" \
    -I"$root/code" "$root/code/wbmp.cpp" "$root/tests/wbmp_reader_self_test.cpp" -o "$reader_out"
"$reader_out"
app_out="${TMPDIR:-/tmp}/mk61_wbmp_app_self_test"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -DMK61_TARGET_PICOCALC=1 "${sanitizer_flags[@]}" \
    -I"$root/code" -I"$root/sdk/portable/include" "$root/code/wbmp.cpp" \
    "$root/tests/wbmp_app_ui_self_test.cpp" -o "$app_out"
"$app_out"
