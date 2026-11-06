#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$root/.build/packed-text-tests"
mkdir -p "$work"
python3 "$root/dev/tools/pack_resident_text.py" --check
sanitizers=()
if [[ "${MK61_TEST_SANITIZERS:-1}" != 0 ]]; then
  sanitizers=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${sanitizers[@]}" \
  -DMK61_TEST_PACKED_TEXT=1 "$root/tests/packed_text_self_test.cpp" \
  "$root/code/packed_text.cpp" "$root/code/mk61_io.cpp" -o "$work/packed-text"
"$work/packed-text"
