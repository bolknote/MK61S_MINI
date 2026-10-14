#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-native-libc.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-1}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang -std=c11 -O2 -Wall -Wextra -Werror -fno-builtin "${flags[@]}" \
  -DMK61_STRING_TEST_BUILD -Dmemchr=mk61_test_memchr -Dstrlen=mk61_test_strlen -Dstrnlen=mk61_test_strnlen \
  -Dstrchr=mk61_test_strchr -Dstrcmp=mk61_test_strcmp -Dstrncmp=mk61_test_strncmp \
  -Dstrcpy=mk61_test_strcpy -Dstrncpy=mk61_test_strncpy -Dstrncat=mk61_test_strncat \
  -c "$root/code/system_strings.c" -o "$work/strings.o"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
  "$root/tests/system_strings_self_test.cpp" "$work/strings.o" -o "$work/strings"
"$work/strings"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
  -DMK61_USE_NATIVE_LIBC=1 -DMK61_ENABLE_LOADABLE_MODULES=1 -I"$root/code" \
  "$root/tests/retained_allocation_self_test.cpp" "$root/code/shared_memory.cpp" -o "$work/retained"
"$work/retained"
