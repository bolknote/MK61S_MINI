#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-shared-buffer.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    "$root/tests/shared_memory_buffer_self_test.cpp" "$root/code/shared_memory_buffer.cpp" -o "$build/test"
"$build/test"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" \
    "$root/tests/picocalc_buffer_services_self_test.cpp" "$root/code/shared_memory_buffer.cpp" -o "$build/app"
"$build/app"
