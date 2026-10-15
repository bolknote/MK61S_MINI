#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-inode-wire.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for scalar in 0 1; do
  flags=()
  if [[ "$scalar" == 1 ]]; then flags=(-DMK61_C9_SCALAR_CODEC=1); fi
  clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${sanitizer_flags[@]}" \
    "${flags[@]}" "$root/tests/c9_inode_wire_self_test.cpp" -o "$build_dir/test"
  "$build_dir/test"
done
