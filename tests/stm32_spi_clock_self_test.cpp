#include "stm32_spi_clock.hpp"

#include <cassert>

int main(void) {
  using namespace stm32_spi_clock;

  assert(prescaler_from_br(0) == 2);
  assert(prescaler_from_br(1) == 4);
  assert(prescaler_from_br(2) == 8);
  assert(prescaler_from_br(7) == 256);
  assert(prescaler_from_br(8) == 0);

  assert(actual_hz(96000000UL, 2) == 12000000UL);
  assert(actual_hz(96000000UL, 1) == 24000000UL);
  assert(actual_hz(84000000UL, 2) == 10500000UL);
  assert(actual_hz(84000000UL, 1) == 21000000UL);
  assert(actual_hz(96000000UL, 8) == 0);
  return 0;
}
