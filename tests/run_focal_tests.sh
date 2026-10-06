#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_focal_self_test"
sanitizer_flags=()
vm_flags=()
vm_sources=()
if [[ "${MK61_LANGUAGE_VM_TEST:-0}" == "1" ]]; then
  vm_flags=(-DMK61_LANGUAGE_VM_TEST)
  vm_sources=("$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp")
fi
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

focal_enabled="${MK61_ENABLE_FOCAL:-}"
if [[ -z "$focal_enabled" ]]; then
  if grep -Eq '^[[:space:]]*#[[:space:]]*define[[:space:]]+MK61_ENABLE_FOCAL[[:space:]]+0([[:space:]]|$)' "$root/code/config.h"; then
    focal_enabled=0
  else
    focal_enabled=1
  fi
fi

if [[ "$focal_enabled" == "0" ]]; then
  echo "focal_self_test: skipped (MK61_ENABLE_FOCAL=0)"
  exit 0
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${vm_flags[@]}" \
  "${sanitizer_flags[@]}" \
  -DFOCAL_HOST_TEST \
  -DFOCAL_SELF_TEST \
  -DMK61_ENABLE_FOCAL="$focal_enabled" \
  -I"$root/code" \
  "$root/tests/focal_self_test.cpp" \
  "$root/code/focal.cpp" \
  "${vm_sources[@]}" \
  -o "$out"

"$out"
