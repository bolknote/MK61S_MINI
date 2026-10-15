#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-zx0-prototypes.XXXXXX")"
trap 'rm -rf "$work"' EXIT
python3 "$root/tests/experimental/prepare_zx0_prototypes.py" --output-dir "$work/variants" > "$work/manifest.json"
clang++ -DMK61_ZX0_WORD_TEST=1 -std=c++17 -O2 -Wall -Wextra -Werror -fno-builtin \
  -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
  -I"$root/code" -I"$root/tests/experimental" \
  "$root/tests/experimental/zx0_candidates_self_test.cpp" \
  "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
  "$work/variants/scalar.cpp" "$work/variants/word.cpp" "$work/variants/dsp.cpp" -o "$work/test"
"$work/test" "$@"
