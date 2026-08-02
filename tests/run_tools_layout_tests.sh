#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
actual="$(
  find "$root/tools" -mindepth 1 -maxdepth 1 -type f ! -name '.*' \
    -exec basename {} \; | LC_ALL=C sort
)"
expected="$(
  printf '%s\n' \
    README.md \
    build_f401_bundle.sh \
    build_fmk_font.sh \
    build_mk61_module_pack.sh \
    build-gcc.cmd \
    mk61-arduino-board.cmd \
    mk61-firmware.cmd \
    mkc.cmd |
    LC_ALL=C sort
)"

if [[ "$actual" != "$expected" ]]; then
  printf 'Unexpected public tools layout.\nExpected:\n%s\nActual:\n%s\n' \
    "$expected" "$actual" >&2
  exit 1
fi

test -f "$root/tools/.mk61-app/mk61_module_pack.cpp"
test -f "$root/tools/.mk61-app/mk61_module.ld"
test -f "$root/tools/.mk61-app/build.ps1"
test -f "$root/tools/.fmk-font/fmk_font.cpp"
test ! -e "$root/tools/fmk_font"
test ! -e "$root/tools/mk61_module_pack"

printf 'tools_layout_tests: ok\n'
