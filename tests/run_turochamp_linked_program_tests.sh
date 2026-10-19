#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-linked-chess.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in 0 1; do
  extra=()
  if [[ "$backend" == 1 ]]; then
    extra=(-Wno-unused -Wno-unused-parameter -Wno-cpp -DMK61_DISPLAY_UC1609
      -include "$root/tests/mk_math_shim/debug.h" -I"$root/tests/mk_math_shim")
    for file in mk_math_core.cpp mk61emu_core.cpp language_workspace.cpp shared_memory.cpp workspace_swap.cpp zx0.cpp zx0_encode.cpp; do
      extra+=("$root/code/$file")
    done
  fi
  clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_MATH_BACKEND="$backend" -I"$root/code" -I"$root/tools" \
    "$root/tests/turochamp_linked_program_self_test.cpp" "$root/code/language_linked_program.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" "${extra[@]}" -o "$work/test-$backend"
  "$work/test-$backend" "$root/programs/games/Turochamp"
done
