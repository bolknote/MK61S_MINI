#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/tests/vfat_diagnostic_tool_self_test.py"
if grep -Eq 'g_last_error|g_error_detail|trace_line_at' "$root/code/virtual_fat.cpp"; then
  printf 'VFAT diagnostic must not reintroduce mutable error strings\n' >&2
  exit 1
fi
out="${TMPDIR:-/tmp}/virtual_fat_self_test"
module_out="${TMPDIR:-/tmp}/virtual_fat_module_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$root/code" \
  "$root/tests/virtual_fat_self_test.cpp" \
  "$root/code/device_identity.cpp" \
  "$root/code/virtual_fat.cpp" \
  "$root/code/virtual_fat_diagnostic.cpp" \
  "$root/code/program_store.cpp" \
  "$root/code/storage_geometry.cpp" \
  "$root/code/language_workspace.cpp" \
  "$root/code/shared_memory.cpp" \
  "$root/code/shared_scratch.cpp" \
  "$root/code/exclusive_buffer.cpp" \
  "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" \
  "$root/code/zx0_encode.cpp" \
  -o "$out"

"$out"

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO_BLACKPILL_F401CC \
  -DMK61_DISPLAY_UC1609=1 \
  -include "$root/tests/program_store_shim/program_store_test_shim.h" \
  -I"$root/tests/program_store_shim" \
  -I"$root/code" \
  "$root/tests/virtual_fat_self_test.cpp" \
  "$root/code/device_identity.cpp" \
  "$root/code/virtual_fat.cpp" \
  "$root/code/virtual_fat_diagnostic.cpp" \
  "$root/code/program_store.cpp" \
  "$root/code/storage_geometry.cpp" \
  "$root/code/language_workspace.cpp" \
  "$root/code/shared_memory.cpp" \
  "$root/code/shared_scratch.cpp" \
  "$root/code/exclusive_buffer.cpp" \
  "$root/code/loadable_module_format.cpp" \
  "$root/code/workspace_swap.cpp" \
  "$root/code/zx0.cpp" \
  "$root/code/zx0_encode.cpp" \
  -o "$module_out"

"$module_out"
