#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-turo-cluster.XXXXXX")"
trap 'rm -rf "$work"' EXIT HUP INT TERM
for backend in 0 1; do
  clang++ -std=c++17 -O2 -Wall -Wextra -Werror -DMK61_MATH_BACKEND="$backend" \
    -I"$root/code" "$root/tests/turochamp_vm_budget_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/budget-$backend"
  "$work/budget-$backend" "$root/programs/games/Turochamp/"*.tbi
done
python3 "$root/tests/hil_turochamp_merge_self_test.py"
