#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-keywait-test.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" \
  -DMK61_KEY_WAIT_BENCHMARK=1 -I"$root/code" \
  "$root/tests/key_wait_benchmark_self_test.cpp" "$root/code/key_wait_benchmark.cpp" -o "$work/test"
"$work/test"
clang++ -std=c++17 -Os -I"$root/code" -c "$root/code/key_wait_benchmark.cpp" -o "$work/disabled.o"
if nm "$work/disabled.o" 2>/dev/null | rg 'key_wait_benchmark'; then
  echo "disabled keywait diagnostics retained runtime code/data" >&2
  exit 1
fi
echo "KEYWAIT benchmark: default build has no diagnostic symbols PASS"
