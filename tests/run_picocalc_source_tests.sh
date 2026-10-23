#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-pico-source.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -DMK61_CORE_STANDALONE=1 \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$root/code" -I"$root/ports/picocalc" \
    "$root/tests/picocalc_source_document_self_test.cpp" "$root/code/shared_memory_buffer.cpp" \
    -o "$build_dir/source-test"
"$build_dir/source-test"
