#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-fat-chain.XXXXXX")"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-O1 -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
for backend in software stm32; do
  backend_flags=()
  if [[ "$backend" == "stm32" ]]; then
    backend_flags=(-DMK61_CRC32_EMULATE_STM32)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror "${sanitizer_flags[@]}" \
    "${backend_flags[@]}" -I"$root/code" \
    "$root/tests/fat_cluster_chain_self_test.cpp" \
    "$root/code/fat_cluster_chain.cpp" -o "$build_dir/$backend"
  "$build_dir/$backend"
done
