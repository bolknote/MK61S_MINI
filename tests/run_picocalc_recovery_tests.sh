#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-pico-recovery.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
for unit in ff ffunicode; do
    clang -std=c11 -O2 "${flags[@]}" -I"$root/ports/picocalc" -I"$root/third_party/fatfs" \
        -c "$root/third_party/fatfs/$unit.c" -o "$work/$unit.o"
done
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" -I"$root/code" -I"$root/ports/picocalc" -I"$root/third_party/fatfs" \
    "$root/tests/picocalc_recovery_self_test.cpp" "$root/ports/picocalc/storage.cpp" \
    "$root/ports/picocalc/storage_journal.cpp" "$root/code/shared_memory_buffer.cpp" \
    "$work/ff.o" "$work/ffunicode.o" -o "$work/recovery"
"$work/recovery"
