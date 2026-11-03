#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
bash "$root/tests/run_explorer_view_tests.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-explorer-app-tests.XXXXXX")"
trap 'rm -rf "$work"' EXIT

python3 "$root/tests/explorer_app_routing_surface.py" \
  "$work/explorer_entry_can_run.inc"

flags=(-std=c++17 -O2 -Wall -Wextra -Werror
  -DMK61_ENABLE_FOCAL=0 -DMK61_ENABLE_TINYBASIC=0
  -DTEXT_EDITOR_HOST_TEST=1
  -I"$work")
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for loader in 0 1; do
  clang++ "${flags[@]}" \
    -DMK61_APP_RUNTIME_AVAILABLE="$loader" \
    "$root/tests/explorer_app_routing_self_test.cpp" \
    -o "$work/explorer-app-$loader"
  "$work/explorer-app-$loader"
done

python3 "$root/tests/explorer_ui_surface.py" "$work"
for unit in explorer_view wbmp builtin_font ERM19264_graphics_font; do
  clang++ "${flags[@]}" -DMK61_CORE_STANDALONE=1 -I"$root/code" \
    -c "$root/code/$unit.cpp" -o "$work/$unit.o"
done
for ui in 0 1; do
for app in 0 1; do
for graphical in 0 1; do
app_flags=()
if [[ "$app" == 1 ]]; then app_flags=(-DMK61_BUILD_EXPLORER_MODULE=1); fi
sources=()
if [[ "$graphical" == 1 ]]; then
  sources=("$work/explorer_view.o" "$work/wbmp.o" "$work/builtin_font.o" "$work/ERM19264_graphics_font.o")
fi
  clang++ "${flags[@]}" -DMK61_PROPORTIONAL_UI_FONTS="$ui" \
    -DMK61_EXPLORER_GRAPHICS="$graphical" -Wno-unused-function \
    "${app_flags[@]}" \
    -I"$root/code" "$root/tests/explorer_ui_self_test.cpp" \
    "$root/code/explorer_autoexec.cpp" \
    "$root/code/app_flow.cpp" \
    "${sources[@]}" \
    -o "$work/explorer-ui"
  "$work/explorer-ui"
done
done
done

echo "explorer APP routing tests passed"
