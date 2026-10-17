#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-integer-span.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=(-std=c++17 -O1 -Wall -Wextra -Werror -DLANGUAGE_VM_TRACE)
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in 0 1; do
  # Same public numeric/control types, independent ordinary evaluator. No new
  # hint can bypass its LOAD fallback when INTEGER_SPAN is compiled out.
  clang++ "${flags[@]}" -DMK61_MATH_BACKEND="$backend" -DMK61_VM_INTEGER_SPAN=0 \
    -Drun=reference_run -Dinspect=reference_inspect -Dinspect_flash=reference_inspect_flash \
    -Dinstruction_end=reference_instruction_end -Dline_pc=reference_line_pc \
    -Dsource_line=reference_source_line -Dsource_column=reference_source_column \
    -Dtrace_following=reference_trace_following -Derror_name=reference_error_name \
    -I"$root/code" -c "$root/code/language_vm.cpp" -o "$work/reference.o"
  clang++ "${flags[@]}" -DMK61_MATH_BACKEND="$backend" -DMK61_VM_INTEGER_SPAN=1 \
    -DLANGUAGE_VM_TEST_INTEGER_SPAN -DLANGUAGE_VM_TEST_INTEGER_SHORT_BLOCK -I"$root/code" \
    "$root/tests/language_vm_integer_span_self_test.cpp" "$root/code/language_bytecode.cpp" \
    "$root/code/language_vm.cpp" "$work/reference.o" -o "$work/test"
  "$work/test"
done
