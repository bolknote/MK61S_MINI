#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_stm32f4_gpio_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for target in STM32F401xC STM32F401xE STM32F411xE STM32F103xB host; do
  definitions=()
  if [[ "$target" != host ]]; then
    definitions=(-DARDUINO_ARCH_STM32 -D"$target")
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" "${definitions[@]}" \
    -I"$root/tests/stm32f4_gpio_shim" -I"$root/code" \
    "$root/tests/stm32f4_gpio_self_test.cpp" "$root/code/stm32f4_gpio.cpp" \
    -o "$out-$target"
  "$out-$target"
done
python3 "$root/tests/hal_timer_policy_self_test.py"
