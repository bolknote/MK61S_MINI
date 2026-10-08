#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-language-vm.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$root/code" "$root/tests/language_vm_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" \
  -o "$work/test"
"$work/test"
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$root/code" "$root/tests/language_resources_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/resources"
"$work/resources"
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$root/code" "$root/tests/language_value_self_test.cpp" -o "$work/values"
"$work/values"
clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$root/code" "$root/tests/language_integer_self_test.cpp" \
  "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" -o "$work/integers"
"$work/integers"
for variant in compact f64; do
  extra=()
  if [[ "$variant" == "f64" ]]; then extra=(-DLANGUAGE_VM_TEST_NO_DECIMAL_RECIPE); fi
  clang++ -std=c++17 -Wall -Wextra -Werror "${flags[@]}" "${extra[@]}" \
    -I"$root/code" "$root/tests/language_vm_input_self_test.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" \
    "$root/code/language_vm_validation.cpp" -o "$work/input-$variant"
  "$work/input-$variant"
done

# Arduino compiles every .cpp, including this experimental compiler when both
# VM placements are off. Its unused APP-only frames must not enter resident
# stack analysis. Host/portable builds and both explicit VM modes retain it.
for placement in disabled resident overlay compiler-module vm-module input-module; do
  extra=()
  if [[ "$placement" == resident ]]; then
    extra=(-DMK61_RESIDENT_LANGUAGE_VM=1)
  elif [[ "$placement" == overlay ]]; then
    extra=(-DMK61_OVERLAY_LANGUAGE_VM=1)
  elif [[ "$placement" == compiler-module ]]; then
    extra=(-DMK61_LANGUAGE_VM_COMPILER=1)
  elif [[ "$placement" == vm-module ]]; then
    extra=(-DMK61_BUILD_LANGUAGE_VM_MODULE=1)
  elif [[ "$placement" == input-module ]]; then
    extra=(-DMK61_BUILD_LANGUAGE_INPUT_MODULE=1)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror -DCONFIG -DARDUINO_ARCH_STM32 \
    "${extra[@]}" -I"$root/code" -c "$root/code/language_bytecode.cpp" \
    -o "$work/compiler-$placement.o"
  symbols="$(nm "$work/compiler-$placement.o")"
  if [[ "$placement" == disabled ]]; then
    [[ "$symbols" != *compile_basic* && "$symbols" != *compile_focal* ]]
  else
    [[ "$symbols" == *compile_basic* && "$symbols" == *compile_focal* ]]
  fi
done
MK61_LANGUAGE_VM_TEST=1 bash "$root/tests/run_tinybasic_tests.sh"
MK61_LANGUAGE_VM_TEST=1 bash "$root/tests/run_focal_tests.sh"
