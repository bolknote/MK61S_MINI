#ifndef MK61_STM32F4_GPIO_HPP
#define MK61_STM32F4_GPIO_HPP

#include <Arduino.h>
#include <stdint.h>

#if defined(ARDUINO_ARCH_STM32) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
  #define MK61_GPIO_USES_STM32F4 1
#else
  #define MK61_GPIO_USES_STM32F4 0
#endif

namespace stm32f4_gpio {

#if MK61_GPIO_USES_STM32F4

// PinName identifies the physical pin; Arduino's Dxx/analog aliases are
// converted at the API boundary. Fixed PinNames can use these masks at compile
// time without a duplicate board pin table or a RAM pin cache.
struct PinDescription {
  uint32_t name;

  constexpr explicit PinDescription(uint32_t physical_pin) : name(physical_pin) {}
  constexpr uint32_t port_index() const { return (name >> 4) & 15U; }
  constexpr uint32_t bit_index() const { return name & 15U; }
  constexpr uint32_t shift() const { return bit_index() * 2U; }
  constexpr uint32_t bit_mask() const { return 1UL << bit_index(); }
  constexpr uint32_t pair_mask() const { return 3UL << shift(); }
  constexpr bool valid() const {
    return (name & ~0x7FFUL) == 0 && port_index() <= (uint32_t) PortH;
  }
  constexpr uint32_t clock_mask() const {
    // F401/F411 number GPIOH immediately after GPIOE in PinName, while
    // RCC keeps the physical H clock at bit 7.
    return port_index() == (uint32_t) PortH ? RCC_AHB1ENR_GPIOHEN :
        (1UL << port_index());
  }
};

// These project pins are never driven by Arduino analogWrite(). The sound
// driver owns and explicitly stops its PWM before reconfiguring its pin.
// Keeping this narrow GPIO API avoids pulling Arduino's PWM/HardwareTimer
// teardown into every GPIO configuration.
void configure(uint32_t pin, uint32_t mode);
void write(uint32_t pin, uint32_t level);
int read(uint32_t pin);

#else

// Dependent calls also allow minimal host Arduino shims to expose only the
// operations a tested component actually uses.
template<typename Pin>
inline void configure(Pin pin, uint32_t mode) { pinMode(pin, mode); }

template<typename Pin>
inline void write(Pin pin, uint32_t level) { digitalWrite(pin, level); }

template<typename Pin>
inline int read(Pin pin) { return digitalRead(pin); }

#endif

} // namespace stm32f4_gpio

#endif
