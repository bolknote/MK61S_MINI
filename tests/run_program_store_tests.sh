#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
bash "$root/tests/run_c9_inode_wire_tests.sh"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-program-store.XXXXXX")"
out="$build_dir/program_store_self_test"
python3 "$root/tests/app_memory_surface.py" "$build_dir/app_memory_acquire.inc"
capacity_flags=()
if [[ "${1:-}" == --stage-max-capacity ]]; then
  capacity_flags=(-DMK61_TEST_FLASH_MAX_CAPACITY_BYTES=134217728)
fi
shared_flags=()
if [[ "${MK61_TEST_STORAGE_SHARED_TEMP:-0}" == 1 ]]; then
  shared_flags=(-DMK61_STORAGE_SHARED_TEMP=1)
fi
if [[ "${MK61_TEST_SCOPED_RESIDENT_BUFFERS:-0}" == 1 ]]; then
  shared_flags+=(-DMK61_SCOPED_RESIDENT_BUFFERS=1)
  if [[ "${MK61_TEST_STORAGE_SHARED_TEMP:-0}" == 1 ]]; then
    # The old 1536-byte payload lived outside simulated_ram. Credit its move
    # into that pool while charging 64 bytes for the new host handle/manager.
    # All APP/stage/MSC sizes and existing assertions remain unchanged.
    shared_flags+=(-DMK61_TEST_RAM_SIZE=34240)
  fi
fi
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-O1 -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi

for backend in software stm32; do
  backend_flags=()
  if [[ "$backend" == "stm32" ]]; then
    backend_flags=(-DMK61_CRC32_EMULATE_STM32)
  else
    # Exercise graphical activity scopes as well as the no-graphics build.
    backend_flags=(-DMK61_ENABLE_USB_SCREEN=1)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" "${shared_flags[@]}" "${capacity_flags[@]}" \
    "${backend_flags[@]}" \
    -DARDUINO_BLACKPILL_F401CC \
    -include "$root/tests/program_store_shim/program_store_test_shim.h" \
    -I"$root/tests/program_store_shim" \
    -I"$build_dir" \
    -I"$root/code" \
    "$root/tests/program_store_self_test.cpp" \
    "$root/code/explorer_autoexec.cpp" \
    "$root/code/loadable_module_system_app.cpp" \
    "$root/code/loadable_module_format.cpp" \
    "$root/code/program_store.cpp" "$root/code/storage_workspace.cpp" \
    "$root/code/shared_memory.cpp" \
    "$root/code/storage_geometry.cpp" \
  "$root/code/fat_cluster_chain.cpp" \
    "$root/code/storage_path.cpp" \
    "$root/code/shared_scratch.cpp" \
    "$root/code/exclusive_buffer.cpp" \
    "$root/code/workspace_swap.cpp" \
    "$root/code/zx0.cpp" \
    "$root/code/zx0_encode.cpp" \
    "$root/code/fmk_font.cpp" "$root/code/fmk_prepare.cpp" "$root/code/prepared_font.cpp" \
    -o "$out-$backend"

  "$out-$backend" "$@"
done

# The normal matrix above intentionally models the 64 KiB F401 product.  One
# additional native build exercises F411's 8 KiB FMK quota and its multi-sector
# C9 large-file path; otherwise a parser-only size increase could pass CI while
# USB imports of a real large font still fail on hardware.
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" "${shared_flags[@]}" "${capacity_flags[@]}" \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$build_dir" \
  -I"$root/code" \
  "$root/tests/program_store_self_test.cpp" \
  "$root/code/explorer_autoexec.cpp" \
  "$root/code/loadable_module_system_app.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/program_store.cpp" "$root/code/storage_workspace.cpp" \
  "$root/code/shared_memory.cpp" \
  "$root/code/storage_geometry.cpp" \
  "$root/code/fat_cluster_chain.cpp" \
  "$root/code/storage_path.cpp" \
  "$root/code/shared_scratch.cpp" \
  "$root/code/exclusive_buffer.cpp" \
  "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" \
  "$root/code/zx0_encode.cpp" \
  "$root/code/fmk_font.cpp" "$root/code/fmk_prepare.cpp" "$root/code/prepared_font.cpp" \
  -o "$out-f411-font"

"$out-f411-font" "$@"
