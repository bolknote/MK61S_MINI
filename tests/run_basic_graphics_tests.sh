#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-basic-graphics.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" \
  "$root/tests/basic_graphics_self_test.cpp" "$root/code/basic_graphics.cpp" -o "$work/raster"
"$work/raster"
for graphics in 0 1; do
  clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_HAS_COMPILED_GRAPHICS="$graphics" \
    -include "$root/tests/basic_graphics_runtime_fixture.hpp" -I"$root/code" \
    "$root/tests/basic_graphics_runtime_self_test.cpp" \
    "$root/code/basic_graphics_runtime.cpp" "$root/code/basic_graphics.cpp" \
    -o "$work/runtime"
  "$work/runtime"
  # Real native allocator: cold USB/APP pinning must not forbid lazy graphics.
  # A tight pool also covers a larger APP starting after a small hot VM.
  for pool in 49152 43712; do
    clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_HAS_COMPILED_GRAPHICS="$graphics" \
    -DBASIC_GRAPHICS_REAL_SHARED_MEMORY -DMK61_SCOPED_RESIDENT_BUFFERS=1 \
    -DMK61_USE_NATIVE_LIBC=1 -DMK61_ENABLE_LOADABLE_MODULES=1 \
    -DMK61_ENABLE_USB_SCREEN=1 -DMK61_TEST_RAM_SIZE="$pool" \
    -include "$root/tests/basic_graphics_runtime_fixture.hpp" -I"$root/code" \
    "$root/tests/basic_graphics_cold_usb_self_test.cpp" \
    "$root/code/basic_graphics_runtime.cpp" "$root/code/basic_graphics.cpp" \
    "$root/code/shared_memory.cpp" -o "$work/cold-usb"
    "$work/cold-usb"
    "$work/cold-usb" small-vm
  done
done
bash "$root/tests/run_tinybasic_tests.sh"
MK61_LANGUAGE_VM_TEST=1 bash "$root/tests/run_tinybasic_tests.sh"
