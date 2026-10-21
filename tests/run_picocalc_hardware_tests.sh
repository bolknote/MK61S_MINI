#!/usr/bin/env bash
set -euo pipefail
python3 "$(dirname "$0")/picocalc_psram_pio_self_test.py"
python3 "$(dirname "$0")/picocalc_psram_qpi_self_test.py"
bash "$(dirname "$0")/run_shared_memory_buffer_tests.sh"
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-pico-hardware.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_hardware_self_test.cpp" "$root/ports/picocalc/psram.cpp" \
    "$root/ports/picocalc/external_cache.cpp" "$root/ports/picocalc/dma_support.cpp" \
    "$root/ports/picocalc/buffers.cpp" "$root/code/shared_memory_buffer.cpp" -o "$build/test"
"$build/test"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_transfer_self_test.cpp" -o "$build/transfers"
"$build/transfers"
