#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-mixed-cache.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-1}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" \
  "$root/tests/language_vm_mixed_cache_self_test.cpp" -o "$work/handles"
"$work/handles"
for math in 0 1; do
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror "${flags[@]}" \
  -DMK61_MATH_BACKEND="$math" -I"$root/code" \
  "$root/tests/language_vm_mixed_execute_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/execute-$math"
"$work/execute-$math"
for usb in 0 1; do
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror "${flags[@]}" \
  -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DLANGUAGE_VM_HOST_TEST \
  -DMK61_VM_FILE_CACHE=0 -DMK61_LANGUAGE_VM_CACHE_MIXED=1 \
  -DLANGUAGE_VM_TEST_STATE_RESETS -DMK61_ENABLE_USB_SCREEN="$usb" \
  -DMK61_MATH_BACKEND="$math" -DMK61_LANGUAGE_VM_CACHE_DENSITY=1 \
  -DMK61_LANGUAGE_VM_IMAGE_CACHE_BYTES=24576 -I"$root/code" \
  "$root/tests/language_vm_image_cache_self_test.cpp" \
  "$root/code/language_vm_resident.cpp" "$root/code/language_vm.cpp" \
  "$root/code/language_vm_validation.cpp" "$root/code/language_bytecode.cpp" \
  "$root/code/language_vm_flow.cpp" "$root/code/app_flow.cpp" \
  "$root/code/language_compiler_flow.cpp" "$root/code/app_flow_transfer.cpp" \
  "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" -o "$work/cache-$math-$usb"
"$work/cache-$math-$usb"
done
done
