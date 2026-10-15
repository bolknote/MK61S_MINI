#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-service-gaps.XXXXXX")"
trap 'rm -rf "$work"' EXIT
for detail in 0 1; do
  clang++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -DARDUINO_ARCH_STM32 -DMK61_DWT_SERVICE_GAPS=1 \
    -DMK61_DWT_RUNTIME_DETAIL="$detail" -I"$root/tests/stubs/dwt" -I"$root/code" \
    "$root/tests/dwt_service_gaps_self_test.cpp" "$root/code/dwt_profiler.cpp" \
    -o "$work/probe-$detail"
  "$work/probe-$detail"
done
for flags in "-DMK61_DWT_SERVICE_GAPS=0" "-DMK61_ENABLE_DWT_PROFILER=0 -DMK61_DWT_SERVICE_GAPS=1"; do
  # Deliberately split these controlled compiler flags, not user input.
  clang++ -std=c++17 -Wall -Wextra -Werror $flags -I"$root/code" \
    "$root/tests/dwt_service_gaps_self_test.cpp" -o "$work/disabled"
  "$work/disabled"
done
