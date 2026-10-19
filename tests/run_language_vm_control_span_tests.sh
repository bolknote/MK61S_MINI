#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-control-span.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=(-std=c++17 -O1 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all)
if [[ "${MK61_VM_TEST_PICO_ENTRY:-0}" == 1 ]];then flags+=(-DLANGUAGE_VM_TEST_PICO_ENTRY);fi
for backend in 0 1; do
  for kind in HOST MK61_BUILD_LANGUAGE_VM_MODULE; do
    clang++ "${flags[@]}" -DMK61_MATH_BACKEND="$backend" -D"$kind" \
      -DMK61_VM_INTEGER_BLOCK=0 -DMK61_VM_COMPARE_BLOCK=0 -DMK61_VM_INTEGER_SPAN=0 \
      -Drun=reference_run -Dinspect=reference_inspect -Dinspect_flash=reference_inspect_flash \
      -Dinstruction_end=reference_instruction_end -Dline_pc=reference_line_pc \
      -Dsource_line=reference_source_line -Dsource_column=reference_source_column \
      -Derror_name=reference_error_name -I"$root/code" -c "$root/code/language_vm.cpp" -o "$work/reference.o"
    clang++ "${flags[@]}" -DMK61_MATH_BACKEND="$backend" -D"$kind" -I"$root/code" \
      "$root/tests/language_vm_control_span_self_test.cpp" "$root/code/language_bytecode.cpp" \
      "$root/code/language_vm.cpp" "$work/reference.o" -o "$work/test"
    "$work/test"
  done
done
