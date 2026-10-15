#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-storage-workspace.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for scoped in 0 1; do
  clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${sanitizer_flags[@]}" \
    -DMK61_STORAGE_SHARED_TEMP=1 -DMK61_SCOPED_RESIDENT_BUFFERS="$scoped" \
    "$root/tests/storage_workspace_self_test.cpp" "$root/code/storage_workspace.cpp" \
    "$root/code/shared_memory.cpp" -o "$build_dir/test"
  "$build_dir/test"
done
