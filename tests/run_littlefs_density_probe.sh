#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir=${1:?Pass an official littlefs v2.11.3 checkout}
expected=6cb4e86540eca0d9ba62500a298385c9d863c8be
[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$expected" ]] || { printf 'littlefs revision mismatch\n' >&2; exit 2; }
work=$(mktemp -d "${TMPDIR:-/tmp}/mk61-lfs-probe.XXXXXX")
flags=(-DLFS_NO_MALLOC -DLFS_NO_DEBUG -DLFS_NO_WARN -DLFS_NO_ERROR)
clang -std=c11 -Os "${flags[@]}" -I"$source_dir" -c "$source_dir/lfs.c" -o "$work/lfs.o"
clang -std=c11 -Os "${flags[@]}" -I"$source_dir" -c "$source_dir/lfs_util.c" -o "$work/lfs-util.o"
clang++ -std=c++17 -Os -Wall -Wextra -Werror "${flags[@]}" -I"$source_dir" -I"$root/code" \
  "$root/tests/experimental/littlefs_density_probe.cpp" "$root/code/storage_geometry.cpp" \
  "$work/lfs.o" "$work/lfs-util.o" -o "$work/probe"
"$work/probe"
