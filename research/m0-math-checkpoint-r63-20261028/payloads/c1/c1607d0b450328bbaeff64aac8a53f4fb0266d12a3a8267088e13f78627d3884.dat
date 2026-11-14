#ifndef MK61_STM32_SPI_CLOCK_HPP
#define MK61_STM32_SPI_CLOCK_HPP

#include "rust_types.h"

// STM32F4 кодирует делитель SPI в трёх битах BR как log2(divider) - 1:
// 000=/2, 001=/4, ... 111=/256. Чистые функции держим отдельно от HAL,
// чтобы расчёт частоты аппаратного отчёта проверялся обычным host-тестом.
namespace stm32_spi_clock {

constexpr u8 BR_CODE_MAX = 7;

constexpr u16 prescaler_from_br(u8 br_code) {
  return br_code <= BR_CODE_MAX
      ? (u16) (2U << br_code) : 0;
}

constexpr u32 actual_hz(u32 peripheral_clock_hz, u8 br_code) {
  const u16 prescaler = prescaler_from_br(br_code);
  return prescaler == 0 ? 0 : peripheral_clock_hz / prescaler;
}

} // namespace stm32_spi_clock

#endif
