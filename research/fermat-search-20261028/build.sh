#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "$0")/../.." && pwd)"
task_source="$task_root/research/fermat-search-20261028"
task_build="$task_root/.build/fermat-search-20261028"
mkdir -p "$task_build"
task_prefix="${FERMAT_LIBRARY_PREFIX:-/opt/homebrew}"
if [[ ! -f "$task_prefix/include/mpfr.h" || ! -f "$task_prefix/include/gmpxx.h" ]]; then
  echo "GMP/MPFR headers not found under $task_prefix. Set FERMAT_LIBRARY_PREFIX." >&2
  exit 1
fi
"${CXX:-clang++}" -std=c++17 -O3 -DNDEBUG -Wall -Wextra -Wpedantic -pthread \
  -isystem "$task_prefix/include" "$task_source/fermat-search.cpp" \
  "$task_prefix/lib/libmpfr.a" "$task_prefix/lib/libgmpxx.a" "$task_prefix/lib/libgmp.a" \
  -o "$task_build/fermat-search"
echo "$task_build/fermat-search"
