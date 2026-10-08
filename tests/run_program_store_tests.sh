#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-program-store.XXXXXX")"
out="$build_dir/program_store_self_test"
python3 "$root/tests/app_memory_surface.py" "$build_dir/app_memory_acquire.inc"
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
    "${sanitizer_flags[@]}" \
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

  "$out-$backend" "$@"
done

# The normal matrix above intentionally models the 64 KiB F401 product.  One
# additional native build exercises F411's 8 KiB FMK quota and its multi-sector
# C5 representation; otherwise a parser-only size increase could pass CI while
# USB imports of a real large font still fail on hardware.
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$build_dir" \
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

"$out-f411-font" "$@"
