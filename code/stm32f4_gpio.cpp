#include "stm32f4_gpio.hpp"

#if MK61_GPIO_USES_STM32F4

namespace stm32f4_gpio {
namespace {

static_assert(PortA == 0 && PortB == 1 && PortC == 2 &&
              PortD == 3 && PortE == 4 && PortH == 5,
              "F401/F411 GPIO clock mapping changed");

static GPIO_TypeDef* port_for(PinDescription pin) {
  return pin.valid() ? get_GPIO_Port(pin.port_index()) : NULL;
}

static void enable_clock(PinDescription pin) {
  RCC->AHB1ENR |= pin.clock_mask();
  // STM32 requires a read-back delay after enabling the peripheral clock.
  const volatile uint32_t enabled = RCC->AHB1ENR;
  (void) enabled;
}

} // namespace

void configure_physical(uint32_t name, uint32_t mode) {
  const PinDescription pin(name);
  GPIO_TypeDef* const port = port_for(pin);
  if(port == NULL) return;

  uint32_t direction = 0;
  uint32_t pull = 0;
  bool open_drain = false;
  switch(mode) {
    case INPUT: break;
    case INPUT_PULLUP: pull = 1; break;
    case INPUT_PULLDOWN: pull = 2; break;
    case INPUT_ANALOG: direction = 3; break;
    case OUTPUT: direction = 1; break;
    case OUTPUT_OPEN_DRAIN: direction = 1; open_drain = true; break;
    default: return;
  }

  enable_clock(pin);
  const uint32_t pair = pin.pair_mask();
  const uint32_t shift = pin.shift();
  // Match STM32duino's very-high speed selection. Preserve the output type
  // for input/analog modes and leave AFR/ODR and all other pins untouched.
  port->OSPEEDR = (port->OSPEEDR & ~pair) | pair;
  if(direction == 1) {
    port->OTYPER = (port->OTYPER & ~pin.bit_mask()) |
        (open_drain ? pin.bit_mask() : 0U);
  }
  port->PUPDR = (port->PUPDR & ~pair) | (pull << shift);
  port->MODER = (port->MODER & ~pair) | (direction << shift);
}

void configure(uint32_t digital_pin, uint32_t mode) {
  configure_physical((uint32_t)digitalPinToPinName(digital_pin), mode);
}

void write(uint32_t digital_pin, uint32_t level) {
  const PinDescription pin((uint32_t) digitalPinToPinName(digital_pin));
  GPIO_TypeDef* const port = port_for(pin);
  if(port != NULL) {
    // Like digitalWriteFast(), writes require an already enabled GPIO clock.
    // BSRR changes only this latch and is atomic against ISR writes.
    port->BSRR = level != LOW ? pin.bit_mask() : pin.bit_mask() << 16;
  }
}

int read(uint32_t digital_pin) {
  const PinDescription pin((uint32_t) digitalPinToPinName(digital_pin));
  GPIO_TypeDef* const port = port_for(pin);
  return port != NULL && (port->IDR & pin.bit_mask()) != 0 ? HIGH : LOW;
}

} // namespace stm32f4_gpio

#endif
