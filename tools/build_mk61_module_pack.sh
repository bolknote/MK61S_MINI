#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
output=${MK61_MODULE_PACK_BIN:-"$root/tools/mk61_module_pack"}
sources=(
  "$root/tools/mk61_module_pack.cpp"
  "$root/code/loadable_module_format.cpp"
  "$root/code/loadable_module_format.hpp"
  "$root/code/zx0.cpp"
  "$root/code/zx0.hpp"
  "$root/code/storage_geometry.hpp"
  "$root/tools/third_party/zx0/zx0.h"
  "$root/tools/third_party/zx0/optimize.c"
  "$root/tools/third_party/zx0/compress.c"
  "$root/tools/third_party/zx0/memory.c"
)

rebuild=0
if [[ ! -x "$output" ]]; then
  rebuild=1
else
  for source in "${sources[@]}"; do
    if [[ "$source" -nt "$output" ]]; then
      rebuild=1
      break
    fi
  done
fi

if [[ "$rebuild" == "1" ]]; then
  mkdir -p "$(dirname "$output")"
  c++ -x c++ -std=c++17 -O2 -Wall -Wextra -Werror \
    -I"$root/code" \
    "$root/tools/mk61_module_pack.cpp" \
    "$root/code/loadable_module_format.cpp" \
    "$root/code/zx0.cpp" \
    "$root/tools/third_party/zx0/optimize.c" \
    "$root/tools/third_party/zx0/compress.c" \
    "$root/tools/third_party/zx0/memory.c" \
    -o "$output"
fi

exec "$output" "$@"
