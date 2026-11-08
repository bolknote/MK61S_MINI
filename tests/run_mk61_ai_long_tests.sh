#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# != 2 || ! -f "$1" ]]; then
    echo "usage: bash tests/run_mk61_ai_long_tests.sh MODEL.MKA LONG.REF" >&2
    exit 2
fi
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-ai-long.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=(-O2 -ffp-contract=off)
if [[ "${MK61_AI_TEST_SANITIZERS:-0}" == 1 ]]; then
    flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang -std=c11 "${flags[@]}" -I"$root/code" -c "$root/code/mk61_ai_kernels.c" -o "$build/kernels.o"
clang++ -std=c++17 "${flags[@]}" -I"$root/code" \
    "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" \
    "$root/code/mk61_ai_tokenizer.cpp" "$build/kernels.o" \
    "$root/tests/mk61_ai_long_oracle.cpp" -o "$build/long-oracle"
"$build/long-oracle" "$1" "$2"
