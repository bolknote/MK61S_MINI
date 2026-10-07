#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-language-overlay.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DLANGUAGE_VM_HOST_TEST \
  -DMK61_DISPLAY_UC1609 -DMK61_ENABLE_USB_SCREEN=1 -I"$root/code" \
  "$root/tests/language_vm_overlay_self_test.cpp" \
  "$root/code/language_vm_resident.cpp" "$root/code/language_vm.cpp" \
  "$root/code/app_flow.cpp" "$root/code/language_vm_flow.cpp" \
  "$root/code/language_compiler_flow.cpp" "$root/code/app_flow_transfer.cpp" \
  "$root/code/language_vm_validation.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/shared_memory.cpp" \
  "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
  -o "$work/test"
"$work/test"
for usb in 0 1; do
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DLANGUAGE_VM_HOST_TEST \
  -DMK61_DISPLAY_UC1609 -DMK61_ENABLE_USB_SCREEN="$usb" -DMK61_SCREEN_BUFFER_LOAN=1 \
  -I"$root/code" "$root/tests/language_vm_overlay_self_test.cpp" \
  "$root/code/language_vm_resident.cpp" "$root/code/language_vm.cpp" \
  "$root/code/app_flow.cpp" "$root/code/language_vm_flow.cpp" \
  "$root/code/language_compiler_flow.cpp" "$root/code/app_flow_transfer.cpp" \
  "$root/code/language_vm_validation.cpp" "$root/code/language_bytecode.cpp" \
  "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" -o "$work/screen-loan"
"$work/screen-loan"
done
# Mini/no-BULK uses the same protected-prefix lifecycle without RAM snapshots.
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DLANGUAGE_VM_HOST_TEST -I"$root/code" \
  "$root/tests/language_vm_overlay_self_test.cpp" \
  "$root/code/language_vm_resident.cpp" "$root/code/language_vm.cpp" \
  "$root/code/app_flow.cpp" "$root/code/language_vm_flow.cpp" \
  "$root/code/language_compiler_flow.cpp" "$root/code/app_flow_transfer.cpp" \
  "$root/code/language_vm_validation.cpp" "$root/code/language_bytecode.cpp" \
  "$root/code/shared_memory.cpp" "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" -o "$work/no-bulk"
"$work/no-bulk"
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DMK61_DISPLAY_UC1609 -I"$root/code" \
  "$root/tests/workspace_partition_self_test.cpp" "$root/code/shared_memory.cpp" \
  "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
  -o "$work/partition"
"$work/partition"
