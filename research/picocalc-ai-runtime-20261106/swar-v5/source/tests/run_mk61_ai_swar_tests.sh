#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# != 1 || ! -f "$1" ]]; then echo 'usage: run_mk61_ai_swar_tests.sh MODEL.MKA' >&2; exit 2; fi
model="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
build="${MK61_AI_SWAR_TEST_BUILD_DIR:-$root/.build/mk61ai-swar-tests}"
mkdir -p "$build"
sanitizers=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then sanitizers=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
flags=(-pthread -std=c++17 -O2 -ffp-contract=off -Wall -Wextra -Werror -I"$root/code")
clang++ "${flags[@]}" "${sanitizers[@]}" "$root/tests/mk61_ai_swar_self_test.cpp" -o "$build/arithmetic"
"$build/arithmetic"
python3 "$root/tools/apps/mk61ai/repack_q4.py" "$model" "$build/MODEL-NIBBLE.MKA" > "$build/repack.json"
clang -std=c11 -O2 "${sanitizers[@]}" -c "$root/code/mk61_ai_kernels.c" -o "$build/kernels.o"
clang++ "${flags[@]}" "${sanitizers[@]}" "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" \
    "$root/code/mk61_ai_tokenizer.cpp" "$build/kernels.o" "$root/tests/mk61_ai_swar_model_test.cpp" -o "$build/model"
"$build/model" "$model" "$build/MODEL-NIBBLE.MKA"
