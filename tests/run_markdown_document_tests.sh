#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/markdown_document_self_test"

c++ -std=c++17 -Wall -Wextra -Wsign-compare -Werror -pedantic \
  "$root/tests/markdown_document_self_test.cpp" \
  "$root/code/markdown_document.cpp" \
  -o "$out"

"$out"
