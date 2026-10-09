#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-system-memory.XXXXXX")"
trap 'rm -rf "$work"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-1}" == 1 ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for backend in scalar words; do
  extra=()
  if [[ "$backend" == words ]]; then extra=(-DMK61_MEMORY_TEST_WORDS); fi
  clang -std=c11 -O3 -Wall -Wextra -Werror -fno-builtin \
    "${sanitizer_flags[@]}" \
    -DMK61_MEMORY_TEST_BUILD "${extra[@]}" \
    -Dmemcpy=mk61_test_memcpy -Dmemcmp=mk61_test_memcmp \
    -Dmemmove=mk61_test_memmove -Dmemset=mk61_test_memset \
    -I"$root/code" -c "$root/code/system_memory.c" -o "$work/$backend.o"
  clang -std=c11 -O3 -Wall -Wextra -Werror -fno-builtin \
    "${sanitizer_flags[@]}" \
    -DMK61_MEMORY_TEST_BUILD "${extra[@]}" \
    -Dmemmove=mk61_test_memmove -Dmemset=mk61_test_memset \
    -I"$root/code" -c "$root/code/system_memory_fill_move.c" -o "$work/$backend-fill-move.o"
  clang++ -std=c++17 -O2 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" \
    -I"$root/code" "$root/tests/system_memory_self_test.cpp" "$work/$backend.o" "$work/$backend-fill-move.o" \
    -o "$work/test-$backend"
  "$work/test-$backend"
done
clang -std=c11 -O3 -Wall -Wextra -Werror -fno-builtin \
  "${sanitizer_flags[@]}" -DMK61_MEMORY_TEST_WORDS \
  -Dmemcpy=mk61_test_memcpy -Dmemcmp=mk61_test_memcmp \
  -Dmemmove=mk61_test_memmove -Dmemset=mk61_test_memset \
  -Dstrlen=mk61_test_strlen -Dstrchr=mk61_test_strchr -Dstrcmp=mk61_test_strcmp \
  -I"$root/code" -c "$root/sdk/portable/memory.c" -o "$work/sdk.o"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" -DMK61_TEST_SDK_MEMORY \
  -I"$root/code" "$root/tests/system_memory_self_test.cpp" "$work/sdk.o" \
  -o "$work/test-sdk"
"$work/test-sdk"
