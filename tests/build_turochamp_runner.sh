#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:-${TMPDIR:-/tmp}/mk61-turochamp-runner}"
python3 "$root/tools/turochamp/assemble.py" --check
extra=()
if [[ "${MK61_LANGUAGE_VM_TEST:-0}" == 1 ]]; then
  extra=(-DMK61_LANGUAGE_VM_TEST "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp")
  if [[ "${MK61_VM_TRACE:-0}" == 1 ]]; then
    extra+=(-DLANGUAGE_VM_TRACE "$root/tests/language_vm_trace.cpp")
  fi
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -DTINYBASIC_HOST_TEST \
  -DTINYBASIC_SELF_TEST -I"$root/code" "$root/tests/turochamp_runner.cpp" \
  "$root/code/tinybasic.cpp" "${extra[@]}" -o "$out"
