#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-language-cache.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DLANGUAGE_VM_HOST_TEST \
  -DMK61_LANGUAGE_VM_IMAGE_CACHE_BYTES=16384 -I"$root/code" \
  "$root/tests/language_vm_image_cache_self_test.cpp" \
  "$root/code/language_vm_resident.cpp" "$root/code/language_vm.cpp" \
  "$root/code/language_vm_validation.cpp" "$root/code/language_bytecode.cpp" \
  "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" -o "$work/cache"
"$work/cache"
