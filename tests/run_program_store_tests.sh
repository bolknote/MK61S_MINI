#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_program_store_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

for backend in software stm32; do
  backend_flags=()
  if [[ "$backend" == "stm32" ]]; then
    backend_flags=(-DMK61_CRC32_EMULATE_STM32)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    "${backend_flags[@]}" \
    -DARDUINO_BLACKPILL_F401CC \
    -include "$root/tests/program_store_shim/program_store_test_shim.h" \
    -I"$root/tests/program_store_shim" \
    -I"$root/code" \
    "$root/tests/program_store_self_test.cpp" \
    "$root/code/explorer_autoexec.cpp" \
    "$root/code/loadable_module_system_app.cpp" \
    "$root/code/loadable_module_format.cpp" \
    "$root/code/program_store.cpp" \
    "$root/code/shared_memory.cpp" \
    "$root/code/storage_geometry.cpp" \
    "$root/code/storage_path.cpp" \
    "$root/code/shared_scratch.cpp" \
    "$root/code/exclusive_buffer.cpp" \
    "$root/code/workspace_swap.cpp" \
    "$root/code/zx0.cpp" \
    "$root/code/zx0_encode.cpp" \
    -o "$out-$backend"

  "$out-$backend"
done

# The normal matrix above intentionally models the 64 KiB F401 product.  One
# additional native build exercises F411's 8 KiB FMK quota and its multi-sector
# C5 representation; otherwise a parser-only size increase could pass CI while
# USB imports of a real large font still fail on hardware.
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$root/code" \
  "$root/tests/program_store_self_test.cpp" \
  "$root/code/explorer_autoexec.cpp" \
  "$root/code/loadable_module_system_app.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/program_store.cpp" \
  "$root/code/shared_memory.cpp" \
  "$root/code/storage_geometry.cpp" \
  "$root/code/storage_path.cpp" \
  "$root/code/shared_scratch.cpp" \
  "$root/code/exclusive_buffer.cpp" \
  "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" \
  "$root/code/zx0_encode.cpp" \
  -o "$out-f411-font"

"$out-f411-font"
