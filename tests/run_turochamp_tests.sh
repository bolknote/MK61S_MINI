#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-turo-tests.XXXXXX")"
trap 'rm -rf "$work"' EXIT HUP INT TERM
test_python="${TUROCHAMP_PYTHON:-python3}"
selfplay=()
if [[ $# == 1 && "$1" == --selfplay ]]; then
  selfplay=(--selfplay)
elif [[ $# != 0 ]]; then
  printf 'Usage: bash tests/run_turochamp_tests.sh [--selfplay]\n' >&2
  exit 2
fi
"$test_python" -c 'import chess'
python3 "$root/tests/turochamp_package_self_test.py"
bash "$root/tests/run_display_font_tests.sh" "$root/programs/games/Turochamp/Turochamp.FMK" --require-ink
for backend in interpreter vm; do
  vm_enabled=0
  if [[ "$backend" == vm ]]; then vm_enabled=1; fi
  MK61_LANGUAGE_VM_TEST="$vm_enabled" bash "$root/tests/build_turochamp_runner.sh" "$work/$backend"
  "$test_python" "$root/tests/turochamp_rules_test.py" --runner "$work/$backend"
  extra=()
  if [[ "$backend" == interpreter ]]; then extra=("${selfplay[@]}"); fi
  "$test_python" "$root/tests/turochamp_game_test.py" --runner "$work/$backend" "${extra[@]}"
  "$test_python" "$root/tests/turochamp_book_test.py" --runner "$work/$backend" "${extra[@]}"
done
