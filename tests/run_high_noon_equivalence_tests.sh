#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-high-noon-equivalence.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -O1 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" \
  "$root/tests/high_noon_equivalence_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/test"
for part in player bart; do
  python3 "$root/tools/m8_codec.py" encode "$root/tests/data/high_noon_before/$part.tbi" "$work/old-$part.tbi"
  python3 "$root/tools/m8_codec.py" encode "$root/programs/games/High Noon/$part.tbi" "$work/$part.tbi"
done
"$work/test" "$work/old-player.tbi" "$work/player.tbi" "$work/old-bart.tbi" "$work/bart.tbi"
