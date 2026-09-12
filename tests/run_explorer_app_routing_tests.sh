#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-explorer-app-tests.XXXXXX")"
trap 'rm -rf "$work"' EXIT

python3 "$root/tests/explorer_app_routing_surface.py" \
  "$work/explorer_entry_can_run.inc"

flags=(-std=c++17 -O2 -Wall -Wextra -Werror
  -DMK61_ENABLE_FOCAL=0 -DMK61_ENABLE_TINYBASIC=0
  -I"$work")
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for loadable_modules in 0 1; do
  clang++ "${flags[@]}" \
    -DMK61_ANY_LOADABLE_MODULE="$loadable_modules" \
    "$root/tests/explorer_app_routing_self_test.cpp" \
    -o "$work/explorer-app-$loadable_modules"
  "$work/explorer-app-$loadable_modules"
done

echo "explorer APP routing tests passed"
