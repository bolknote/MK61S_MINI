#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-language-flash.XXXXXX")"
trap 'rm -rf "$work"' EXIT
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I"$root/code" "$root/tests/language_flash_self_test.cpp" -o "$work/test"
"$work/test"
for backend in 0 1; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -DMK61_MATH_BACKEND="$backend" \
    -I"$root/code" "$root/tests/language_flash_compiler_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/compiler"
  "$work/compiler"
done
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -DLANGUAGE_VM_TEST_COMPARE_BLOCK -I"$root/code" "$root/tests/language_flash_vm_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/vm"
"$work/vm"

# Compiler/reference readers have two windows. Exercise the full VM and I/O
# corpus with the shipping VM/INPUT's single bounded window as well.
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -DLANGUAGE_VM_TEST_COMPARE_BLOCK -DMK61_BUILD_LANGUAGE_VM_MODULE \
  -I"$root/code" "$root/tests/language_flash_vm_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/native-vm"
"$work/native-vm"

for kind in HOST MK61_BUILD_LANGUAGE_VM_MODULE; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-sanitize-recover=all -D"$kind" \
    -I"$root/code" "$root/tests/language_vm_widths_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/widths"
  "$work/widths"
done

for backend in 0 1; do
  for kind in HOST MK61_BUILD_LANGUAGE_VM_MODULE; do
    clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
      -fsanitize=address,undefined -fno-sanitize-recover=all \
      -DMK61_MATH_BACKEND="$backend" -D"$kind" -I"$root/code" \
      "$root/tests/language_vm_fetch_self_test.cpp" "$root/code/language_bytecode.cpp" \
      "$root/code/language_vm.cpp" -o "$work/fetch"
    "$work/fetch"
  done
done

for kind in MK61_BUILD_LANGUAGE_VM_MODULE MK61_BUILD_LANGUAGE_INPUT_MODULE HOST; do
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-omit-frame-pointer -D"$kind" \
    -I"$root/code" "$root/tests/language_flash_reader_self_test.cpp" -o "$work/reader"
  "$work/reader"
done
