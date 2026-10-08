#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_dwt_profiler_self_test"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/tests/dwt_profiler_self_test.cpp" \
  -o "$out"

"$out"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -DARDUINO_ARCH_STM32 -DMK61_DWT_RUNTIME_DETAIL=1 \
  -I"$root/tests/stubs/dwt" -I"$root/code" \
  "$root/tests/dwt_runtime_detail_self_test.cpp" "$root/code/dwt_profiler.cpp" \
  -o "$out-detail"
"$out-detail"
