#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_stm32_driver_self_test"
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
for buzzer_pin in PA0 PB9 PB10; do
"${CXX:-c++}" "${flags[@]}" -DPIN_BUZZER="$buzzer_pin" -std=c++17 -Wall -Wextra -Werror -DCONFIG -DARDUINO_ARCH_STM32 -DSTM32F411xE -D__ARM_ARCH_7EM__ -DMK61_ENABLE_SPI1_ARBITER=1 -DMK61_ENABLE_SPI1_DMA=1 \
  -I"$root/tests/stm32f4_driver_shim" -I"$root/code" \
  "$root/tests/stm32f4_drivers_self_test.cpp" "$root/code/stm32f4_adc.cpp" "$root/code/stm32f4_rtc.cpp" "$root/code/spi1_transport.cpp" "$root/code/spi1_dma.cpp" -o "$out"
"$out"
done
