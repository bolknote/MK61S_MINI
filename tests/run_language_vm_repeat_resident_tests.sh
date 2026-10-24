#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
repeat_work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-repeat-c9.XXXXXX")"
trap 'rm -rf "$repeat_work"' EXIT
python3 "$root/tests/app_memory_surface.py" "$repeat_work/app_memory_acquire.inc"
for math in 0 1; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -DCONFIG -DMK61_OVERLAY_LANGUAGE_VM=1 -DMK61_FLASH_LANGUAGE_VM=1 \
    -DSPI_FLASH -DMK61_C9_ALLOCATION_CACHE=1 -DMK61_PROGRAM_STORE_READ_CHUNK=256 -DDBG_SPIROM=0 \
    -DMK61_LANGUAGE_VM_IMAGE_CACHE_BYTES=0 -DMK61_FLASH_VM_PAGE_CACHE_BYTES=32768 \
    -DLANGUAGE_VM_HOST_TEST -DSTM32F411xE -DMK61_DISPLAY_UC1609 -DMK61_SCREEN_BUFFER_LOAN=0 \
    -DMK61_TEST_RAM_SIZE=131072 -DMK61_MATH_BACKEND="$math" \
    -include "$root/tests/program_store_shim/vm_repeat_test_shim.h" \
    -I"$root/tests/program_store_shim" -I"$repeat_work" -I"$root/code" \
    "$root/tests/language_vm_repeat_resident_self_test.cpp" \
    "$root/code/language_vm_resident.cpp" "$root/code/language_vm_flow.cpp" \
    "$root/code/language_vm_validation.cpp" "$root/code/language_compiler_flow.cpp" \
    "$root/code/app_flow.cpp" "$root/code/app_flow_transfer.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" \
    "$root/code/explorer_autoexec.cpp" "$root/code/loadable_module_system_app.cpp" \
    "$root/code/loadable_module_format.cpp" "$root/code/program_store.cpp" \
    "$root/code/storage_workspace.cpp" "$root/code/shared_memory.cpp" \
    "$root/code/storage_geometry.cpp" "$root/code/fat_cluster_chain.cpp" \
    "$root/code/storage_path.cpp" "$root/code/shared_scratch.cpp" "$root/code/exclusive_buffer.cpp" \
    "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    "$root/code/fmk_font.cpp" "$root/code/fmk_prepare.cpp" "$root/code/prepared_font.cpp" \
    -o "$repeat_work/test"
  "$repeat_work/test"
done
