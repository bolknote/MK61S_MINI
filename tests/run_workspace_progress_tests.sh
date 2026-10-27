#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-workspace-progress.XXXXXX")"
trap 'rm -rf "$work"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi

for variant in scalar word; do
  kernel_flags=()
  if [[ "$variant" == word ]]; then kernel_flags=(-DMK61_ZX0_WORD_TEST=1); fi
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" "${kernel_flags[@]}" -I"$root/code" \
    "$root/tests/zx0_progress_self_test.cpp" \
    "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" -o "$work/codec-$variant"
  "$work/codec-$variant"
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" "${kernel_flags[@]}" -I"$root/code" \
    -DMK61_ENABLE_FOCAL=0 -DMK61_ENABLE_TINYBASIC=0 -DMK61_DISPLAY_UC1609 \
    "$root/tests/workspace_progress_self_test.cpp" \
    "$root/code/exclusive_buffer.cpp" "$root/code/language_workspace.cpp" \
    "$root/code/shared_memory.cpp" "$root/code/shared_scratch.cpp" \
    "$root/code/workspace_swap.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    -o "$work/workspace-$variant"
  "$work/workspace-$variant"
done
