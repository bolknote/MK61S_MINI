#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-explorer-view.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
cat >"$work/policy.cpp" <<'CPP'
#include "explorer_view_config.hpp"
static_assert(MK61_EXPLORER_GRAPHICS == EXPECTED_GRAPHICS, "Explorer profile policy");
CPP
for profile in classic module text-module character compact-override; do
  policy_flags=(); expected=0
  case "$profile" in
    classic) policy_flags=(-DMK61_DISPLAY_UC1609=1); expected=1 ;;
    module) policy_flags=(-DMK61_BUILD_EXPLORER_MODULE=1 -DMK61_PORTABLE_TEXT_ONLY=0); expected=1 ;;
    text-module) policy_flags=(-DMK61_BUILD_EXPLORER_MODULE=1 -DMK61_PORTABLE_TEXT_ONLY=1) ;;
    character) policy_flags=(-DMK61_LCD1602_A00=1) ;;
    compact-override) policy_flags=(-DMK61_BUILD_EXPLORER_MODULE=1 -DMK61_EXPLORER_GRAPHICS=0) ;;
  esac
  clang++ -std=c++17 -Wall -Wextra -Werror -fsyntax-only -I"$root/code" \
    "${policy_flags[@]}" -DEXPECTED_GRAPHICS="$expected" "$work/policy.cpp"
done
if clang++ -std=c++17 -fsyntax-only -I"$root/code" -DMK61_EXPLORER_GRAPHICS=2 \
    -DEXPECTED_GRAPHICS=2 "$work/policy.cpp" >"$work/invalid-policy.log" 2>&1; then
  echo 'Explorer accepted an invalid graphics policy' >&2; exit 1
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -DMK61_CORE_STANDALONE=1 "${flags[@]}" \
  -I"$root/code" "$root/tests/explorer_view_self_test.cpp" "$root/code/explorer_view.cpp" \
  "$root/code/wbmp.cpp" "$root/code/builtin_font.cpp" "$root/code/ui_font.cpp" \
  "$root/code/ERM19264_graphics_font.cpp" -o "$work/test"
"$work/test" "$@"
