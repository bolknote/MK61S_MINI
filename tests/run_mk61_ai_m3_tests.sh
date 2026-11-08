#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
ai_build="$root/.build/mk61ai/m3-linear/tests"
mkdir -p "$ai_build"
ai_flags=(-O2 -g -ffp-contract=off -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer)
clang -std=c11 "${ai_flags[@]}" -I"$root/sdk/coproc" \
  -c "$root/examples/portable-apps/MK61AI/m3_linear_module.c" -o "$ai_build/module.o"
clang -std=c11 "${ai_flags[@]}" -I"$root/sdk/coproc" -Dmodule_entry=module_int8_entry \
  -c "$root/examples/portable-apps/MK61AI/m3_int8_module.c" -o "$ai_build/int8-module.o"
clang -std=c11 "${ai_flags[@]}" -c "$root/code/mk61_ai_kernels.c" -o "$ai_build/kernels.o"
clang++ -std=c++17 -pthread "${ai_flags[@]}" -I"$root/code" -I"$root/sdk/coproc" \
  -I"$root/examples/portable-apps/MK61AI" \
  "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" "$root/code/mk61_ai_tokenizer.cpp" \
  "$root/tests/mk61_ai_m3_self_test.cpp" "$ai_build/module.o" "$ai_build/kernels.o" -o "$ai_build/m3-test"
"$ai_build/m3-test" "${1:-$root/.build/mk61ai/bundle/sd/AI/MODEL.MKA}"
ai_runtime="$root/research/picocalc-stm32-runtime-20261107/southbridge/runtime"
clang -std=c11 "${ai_flags[@]}" -I"$root/sdk/coproc" -I"$ai_runtime" \
  -c "$ai_runtime/stm3_runtime.c" -o "$ai_build/stm3_runtime.o"
clang -std=c11 "${ai_flags[@]}" -I"$root/sdk/coproc" \
  -c "$root/sdk/coproc/stm3_client.c" -o "$ai_build/client.o"
clang++ -std=c++17 -pthread -DPICO_ON_DEVICE=1 "${ai_flags[@]}" \
  -I"$root/tests/stubs/ai_m3" -I"$root/code" -I"$root/ports/picocalc" \
  -I"$root/sdk/coproc" -I"$ai_runtime" \
  "$root/ports/picocalc/ai_m3.cpp" "$root/tests/picocalc_ai_m3_transport_self_test.cpp" \
  "$root/code/mk61_ai_model.cpp" "$root/code/mk61_ai_linear.cpp" "$root/code/mk61_ai_tokenizer.cpp" "$ai_build/kernels.o" \
  "$ai_build/module.o" "$ai_build/int8-module.o" "$ai_build/client.o" "$ai_build/stm3_runtime.o" \
  -o "$ai_build/transport-test"
"$ai_build/transport-test" "$root/.build/mk61ai/m3-linear/module/M3LINE.S3M" "$root/.build/mk61ai/m3-int8/module/M3LINE.S3M" "$root/.build/mk61ai/swar-v5/MODEL-NIBBLE.MKA"
