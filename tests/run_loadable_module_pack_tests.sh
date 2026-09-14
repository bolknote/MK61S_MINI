#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-module-pack.XXXXXX")"
trap 'rm -rf "$work"' EXIT

packer="$work/mk61_module_pack"
out="$work/loadable_module_pack_self_test"
wrapper_packer="$work/wrapper/mk61_module_pack"
default_packer="$root/.build/tools/mk61_module_pack"
MK61_MODULE_PACK_BIN="$wrapper_packer" \
  "$root/tools/build_mk61_module_pack.sh" --help >/dev/null 2>&1
test -x "$wrapper_packer"
"$root/tools/build_mk61_module_pack.sh" --help >/dev/null 2>&1
test -x "$default_packer"
test ! -e "$root/tools/mk61_module_pack"

if command -v pwsh >/dev/null 2>&1; then
  powershell_packer="$work/powershell/mk61_module_pack"
  MK61_HOST_CXX=clang++ pwsh -NoLogo -NoProfile -File \
    "$root/tools/.mk61-app/build.ps1" \
    -OutputPath "$powershell_packer" >/dev/null
  test -x "$powershell_packer"
  "$powershell_packer" --help >/dev/null 2>&1
fi

clang++ -x c++ -std=c++17 -Wall -Wextra -Werror -O2 \
  -I"$root/code" \
  "$root/tools/.mk61-app/mk61_module_pack.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/zx0.cpp" \
  "$root/tools/.mk61-app/third_party/zx0/optimize.c" \
  "$root/tools/.mk61-app/third_party/zx0/compress.c" \
  "$root/tools/.mk61-app/third_party/zx0/memory.c" \
  -o "$packer"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/tests/loadable_module_pack_self_test.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/zx0.cpp" \
  -o "$out"

"$out" --generate "$work/image.bin"
: > "$work/empty.rel"

if "$packer" \
    --kind app \
    --image "$work/image.bin" \
    --relocations "$work/empty.rel" \
    --memory-size 10512 \
    --entry-offset 0 \
    --load-address 0x20001000 \
    --output "$work/wrong-address.app" >/dev/null 2>&1; then
  printf 'packer unexpectedly accepted a non-virtual load address\n' >&2
  exit 1
fi

"$packer" \
  --kind focal \
  --image "$work/image.bin" \
  --relocations "$work/empty.rel" \
  --memory-size 10512 \
  --entry-offset 0 \
  --output "$work/focal.app"

"$out" "$work/focal.app" "$work/image.bin"

"$packer" \
  --kind app \
  --image "$work/image.bin" \
  --relocations "$work/empty.rel" \
  --memory-size 10512 \
  --entry-offset 0 \
  --output "$work/demo.app"

"$out" "$work/demo.app" "$work/image.bin" app

"$packer" \
  --kind chip8 \
  --image "$work/image.bin" \
  --relocations "$work/empty.rel" \
  --memory-size 10512 \
  --entry-offset 0 \
  --handled-magic C1 \
  --output "$work/chip8.app"

"$out" "$work/chip8.app" "$work/image.bin" chip8

"$packer" \
  --kind markdown-viewer \
  --image "$work/image.bin" \
  --relocations "$work/empty.rel" \
  --memory-size 10512 \
  --entry-offset 0 \
  --handled-magic T2 \
  --output "$work/markdown.app"

"$out" "$work/markdown.app" "$work/image.bin" markdown

if "$packer" \
    --kind chip8 \
    --image "$work/image.bin" \
    --relocations "$work/empty.rel" \
    --memory-size 10512 \
    --entry-offset 0 \
    --handled-magic '!1' \
    --output "$work/invalid-magic.app" >/dev/null 2>&1; then
  printf 'packer unexpectedly accepted non-alphanumeric handled magic\n' >&2
  exit 1
fi
