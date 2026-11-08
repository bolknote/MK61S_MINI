#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
spec_build="${MK61_AI_SPEC_BUILD_DIR:-$root/.build/mk61ai/spec-tests}"
mkdir -p "$spec_build"
flags=()
if [[ "${MK61_AI_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang -std=c11 -O2 "${flags[@]}" -c "$root/code/mk61_ai_kernels.c" -o "$spec_build/kernels.o"
clang++ -std=c++17 -O2 -ffp-contract=off -pthread -Wall -Wextra -Werror \
  -Wno-unused-parameter -Wno-unused-variable -Wno-unused-function "${flags[@]}" \
  -DMK61_CORE_STANDALONE=1 -DMK61_CORE_HOT_TABLES_IN_SRAM=0 -I"$root/code" \
  "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" "$root/code/mk61_ai_tokenizer.cpp" \
  "$root/code/mk61_ai_agent.cpp" "$root/code/mk61_ai_grammar.cpp" "$root/code/mk61_ai_spec.cpp" \
  "$root/code/mk61_ai_harness.cpp" "$root/code/mk61_ai_tools.cpp" "$root/code/mk61emu_core.cpp" \
  "$root/tests/mk61_ai_spec_self_test.cpp" "$spec_build/kernels.o" -o "$spec_build/spec-test"
"$spec_build/spec-test" "$1" "${2:-$root/tests/data/mk61_ai_spec_native.tsv}"
