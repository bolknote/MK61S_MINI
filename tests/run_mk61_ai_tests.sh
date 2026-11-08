#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# != 1 || ! -f "$1" ]]; then
    echo "usage: bash tests/run_mk61_ai_tests.sh /path/to/MODEL.MKA" >&2
    exit 2
fi
ai_package="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
ai_build="${MK61_AI_TEST_BUILD_DIR:-$root/.build/mk61ai/tests}"
mkdir -p "$ai_build"
ai_sanitizers=()
if [[ "${MK61_AI_TEST_SANITIZERS:-0}" == 1 ]]; then
    ai_sanitizers=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
ai_flags=(-pthread -std=c++17 -O2 -ffp-contract=off -Wall -Wextra -Werror
    -Wno-unused-variable -Wno-unused-parameter -Wno-unused-function
    -DMK61_CORE_STANDALONE=1 -DMK61_CORE_HOT_TABLES_IN_SRAM=0 -I"$root/code")
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" -I"$root/ports/picocalc" \
    "$root/tests/mk61_ai_stress_self_test.cpp" -o "$ai_build/stress-test"
"$ai_build/stress-test"
clang -std=c11 -O2 -Wall -Wextra -Werror "${ai_sanitizers[@]}" \
    -c "$root/code/mk61_ai_kernels.c" -o "$ai_build/kernels.o"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" \
    "$root/code/mk61_ai_harness.cpp" "$root/code/mk61_ai_tools.cpp" "$root/code/mk61emu_core.cpp" \
    "$root/tests/mk61_ai_harness_self_test.cpp" -o "$ai_build/harness-test"
"$ai_build/harness-test" "$root/tests/data/mk61_ai_session_v1.bin"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" \
    "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" "$root/code/mk61_ai_tokenizer.cpp" "$ai_build/kernels.o" \
    "$root/code/mk61_ai_harness.cpp" "$root/code/mk61_ai_tools.cpp" "$root/code/mk61_ai_agent.cpp" "$root/code/mk61_ai_grammar.cpp" "$root/code/mk61_ai_spec.cpp" \
    "$root/code/mk61emu_core.cpp" "$root/tests/mk61_ai_controller_self_test.cpp" -o "$ai_build/controller-test"
"$ai_build/controller-test" "$ai_package"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" \
    "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" "$root/code/mk61_ai_tokenizer.cpp" "$ai_build/kernels.o" \
    "$root/code/mk61_ai_harness.cpp" "$root/code/mk61_ai_tools.cpp" "$root/code/mk61_ai_agent.cpp" "$root/code/mk61_ai_grammar.cpp" "$root/code/mk61_ai_spec.cpp" \
    "$root/code/mk61emu_core.cpp" "$root/tests/mk61_ai_agent_self_test.cpp" -o "$ai_build/agent-test"
"$ai_build/agent-test" "$ai_package"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" -pthread \
    "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" \
    "$root/code/mk61_ai_tokenizer.cpp" "$ai_build/kernels.o" \
    "$root/tests/mk61_ai_parallel_self_test.cpp" -o "$ai_build/parallel-test"
"$ai_build/parallel-test" "$ai_package"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" \
    "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" \
    "$root/code/mk61_ai_tokenizer.cpp" "$ai_build/kernels.o" \
    "$root/tests/mk61_ai_prefetch_self_test.cpp" -o "$ai_build/prefetch-test"
"$ai_build/prefetch-test" "$ai_package"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" -I"$root/ports/picocalc" \
    "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" \
    "$root/code/mk61_ai_tokenizer.cpp" "$ai_build/kernels.o" \
    "$root/tests/mk61_ai_presentation_self_test.cpp" -o "$ai_build/presentation-test"
"$ai_build/presentation-test" "$ai_package"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" \
    "$root/tests/mk61_ai_half_product_self_test.cpp" -o "$ai_build/half-product-test"
"$ai_build/half-product-test"
clang++ "${ai_flags[@]}" "${ai_sanitizers[@]}" -DMK61_USE_M0_EABI=1 \
    "$root/code/native_eabi_m0.cpp" "$root/tests/mk61_ai_exact_fp32_self_test.cpp" \
    -o "$ai_build/exact-fp32-test"
"$ai_build/exact-fp32-test"
if [[ -n "${MK61_AI_REFERENCE_PYTHON:-}" ]]; then
    if [[ "${MK61_AI_TEST_SANITIZERS:-0}" == 1 ]]; then
        echo "Run Python parity separately without sanitizers." >&2
        exit 2
    fi
    clang++ "${ai_flags[@]}" -fPIC -shared "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" \
        "$root/code/mk61_ai_tokenizer.cpp" "$root/tests/mk61_ai_model_probe.cpp" \
        "$ai_build/kernels.o" -o "$ai_build/model-probe.dylib"
    ai_reference_args=(--package "$ai_package" --library "$ai_build/model-probe.dylib")
    if [[ -n "${MK61_AI_HF:-}" ]]; then ai_reference_args+=(--hf "$MK61_AI_HF"); fi
    if [[ -n "${MK61_AI_WEIGHTS:-}" ]]; then ai_reference_args+=(--weights "$MK61_AI_WEIGHTS"); fi
    "$MK61_AI_REFERENCE_PYTHON" "$root/tests/mk61_ai_model_test.py" "${ai_reference_args[@]}"
fi
