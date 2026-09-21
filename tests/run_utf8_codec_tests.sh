#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$(mktemp "${TMPDIR:-/tmp}/mk61-utf8-codec.XXXXXX")"
trap 'rm -f "$out"' EXIT HUP INT TERM

flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

python3 "$root/tools/generate_mk8_strings.py" --check

clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$root/code" "$root/tests/utf8_codec_self_test.cpp" -o "$out"
"$out"
