#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-explorer-view.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -DMK61_CORE_STANDALONE=1 "${flags[@]}" \
  -I"$root/code" "$root/tests/explorer_view_self_test.cpp" "$root/code/explorer_view.cpp" \
  "$root/code/wbmp.cpp" "$root/code/builtin_font.cpp" "$root/code/ui_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" -o "$work/test"
"$work/test" "$@"
