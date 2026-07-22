#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-module-pack.XXXXXX")"
trap 'rm -rf "$work"' EXIT

packer="$work/mk61_module_pack"
out="$work/loadable_module_pack_self_test"
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

"$packer" \
  --kind focal \
  --resident "$work/resident.bin" \
  --image "$work/image.bin" \
  --memory-size 10512 \
  --entry-offset 0 \
  --require-zx0 \
  --output "$work/focal.mkmod"

"$out" "$work/focal.mkmod" "$work/image.bin" "$work/resident.bin"
