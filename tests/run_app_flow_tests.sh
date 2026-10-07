#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-app-flow.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=(-Wall -Wextra -Werror)
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 "${flags[@]}" -I"$root/code" \
  "$root/tests/app_flow_self_test.cpp" "$root/code/app_flow.cpp" -o "$work/test"
"$work/test"
clang -std=c11 "${flags[@]}" -I"$root/code" \
  "$root/tests/app_flow_c_self_test.c" -o "$work/c-wire"
"$work/c-wire"
python3 "$root/tests/app_flow_runtime_surface.py" "$work/app_flow_runtime.inc"
clang++ -std=c++17 "${flags[@]}" -I"$root/code" -I"$work" \
  "$root/tests/app_flow_runtime_self_test.cpp" -o "$work/runtime"
"$work/runtime"
