#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-source-stream.XXXXXX")"
trap 'rm -rf "$work"' EXIT
for backend in 0 1; do
clang++ -std=c++17 -O1 -Wall -Wextra -Werror -DMK61_MATH_BACKEND="$backend" \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I"$root/code" "$root/tests/language_source_stream_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/test-$backend"
"$work/test-$backend"
done
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I"$root/code" "$root/tests/language_source_document_self_test.cpp" -o "$work/editor"
"$work/editor"
