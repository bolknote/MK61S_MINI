#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-module-pack.XXXXXX")"
trap 'rm -rf "$work"' EXIT

packer="$work/mk61_module_pack"
out="$work/loadable_module_pack_self_test"
wrapper_packer="$work/wrapper/mk61_module_pack"
MK61_MODULE_PACK_BIN="$wrapper_packer" \
  "$root/tools/build_mk61_module_pack.sh" --help >/dev/null 2>&1
test -x "$wrapper_packer"

clang++ -x c++ -std=c++17 -Wall -Wextra -Werror -O2 \
  -I"$root/code" \
  "$root/tools/mk61_module_pack.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/zx0.cpp" \
  "$root/tools/third_party/zx0/optimize.c" \
  "$root/tools/third_party/zx0/compress.c" \
  "$root/tools/third_party/zx0/memory.c" \
  -o "$packer"

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/tests/loadable_module_pack_self_test.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/zx0.cpp" \
  -o "$out"

"$out" --generate "$work/resident.bin" "$work/image.bin"

if "$packer" \
    --kind app \
    --resident "$work/resident.bin" \
    --image "$work/image.bin" \
    --memory-size 10512 \
    --entry-offset 0 \
    --output "$work/missing-address.app" >/dev/null 2>&1; then
  printf 'packer unexpectedly accepted an APP without --load-address\n' >&2
  exit 1
fi

"$packer" \
  --kind focal \
  --resident "$work/resident.bin" \
  --image "$work/image.bin" \
  --memory-size 10512 \
  --entry-offset 0 \
  --load-address 0x2000B000 \
  --require-zx0 \
  --output "$work/focal.app"

"$out" "$work/focal.app" "$work/image.bin" "$work/resident.bin"

"$packer" \
  --kind app \
  --resident "$work/resident.bin" \
  --image "$work/image.bin" \
  --memory-size 10512 \
  --entry-offset 0 \
  --load-address 0x2000B000 \
  --require-zx0 \
  --output "$work/demo.app"

"$out" "$work/demo.app" "$work/image.bin" "$work/resident.bin" app
