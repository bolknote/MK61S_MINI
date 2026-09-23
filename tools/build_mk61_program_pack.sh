#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
vendor="$root/tools/.mk61-app/third_party/zx0"
output=${MK61_PROGRAM_PACK_BIN:-"$root/.build/tools/mk61_program_pack"}
host_cxx=${MK61_HOST_CXX:-c++}
sources=("$root/tools/.mk61-app/mk61_program_pack.cpp"
  "$root/code/base91.cpp" "$root/code/zx0.cpp"
  "$vendor/optimize.c" "$vendor/compress.c" "$vendor/memory.c")
rebuild=0
if [[ ! -x "$output" ]]; then
  rebuild=1
else
  for source in "${sources[@]}" "$root/code/base91.hpp" "$root/code/zx0.hpp" \
      "$root/code/crc32.hpp" "$vendor/zx0.h"; do
    if [[ "$source" -nt "$output" ]]; then rebuild=1; break; fi
  done
fi
if [[ "$rebuild" == 1 ]]; then
  mkdir -p "$(dirname "$output")"
  "$host_cxx" -x c++ -std=c++17 -O2 -Wall -Wextra -Werror \
    -I"$root/code" -I"$vendor" "${sources[@]}" -o "$output"
fi
exec "$output" "$@"
