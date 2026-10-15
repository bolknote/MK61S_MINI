#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-file-cache.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
flags+=("-DMK61_LANGUAGE_VM_CACHE_MIXED=${MK61_VM_CACHE_MIXED_TEST:-0}")
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$root/code" "$root/tests/language_vm_file_cache_self_test.cpp" \
  "$root/code/language_vm_file_cache.cpp" "$root/code/language_bytecode.cpp" \
  "$root/code/language_vm.cpp" "$root/code/loadable_module_format.cpp" \
  "$root/code/zx0.cpp" -o "$work/test"
"$work/test"
for math in 0 1; do
for usb in 0 1; do
clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" \
  -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DLANGUAGE_VM_HOST_TEST \
  -DLANGUAGE_VM_TEST_STATE_RESETS -DLANGUAGE_VM_TEST_FILE_CACHE \
  -DMK61_BUILD_VM_FILE_CACHE_MODULE -DMK61_VM_FILE_CACHE=1 \
  -DMK61_MATH_BACKEND="$math" -DMK61_ENABLE_USB_SCREEN="$usb" \
  -DMK61_LANGUAGE_VM_IMAGE_CACHE_BYTES="${MK61_VM_CACHE_BYTES_TEST:-24576}" -DMK61_LANGUAGE_VM_CACHE_DENSITY=1 \
  -I"$root/code" -I"$root/sdk/portable/include" \
  "$root/tests/language_vm_file_cache_flow_self_test.cpp" \
  "$root/code/language_vm_resident.cpp" "$root/code/language_vm.cpp" \
  "$root/code/language_vm_validation.cpp" "$root/code/language_bytecode.cpp" \
  "$root/code/language_vm_flow.cpp" "$root/code/app_flow.cpp" \
  "$root/code/language_compiler_flow.cpp" "$root/code/app_flow_transfer.cpp" \
  "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" "$root/code/language_workspace.cpp" \
  "$root/code/language_vm_file_cache.cpp" "$root/code/language_vm_file_cache_entry.cpp" \
  "$root/code/loadable_module_format.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
  -o "$work/flow-$math-$usb"
"$work/flow-$math-$usb"
done
done
