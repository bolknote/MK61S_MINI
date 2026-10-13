#ifndef MK61_GPIO_TEST_ARDUINO_H
#define MK61_GPIO_TEST_ARDUINO_H

#include <assert.h>
#include <stddef.h>
#include <stdint.h>

enum { LOW = 0, HIGH = 1, INPUT = 0, OUTPUT = 1, INPUT_PULLUP = 2,
       INPUT_PULLDOWN = 3, OUTPUT_OPEN_DRAIN = 4, INPUT_ANALOG = 5 };

#if defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE)

enum { PortA, PortB, PortC, PortD, PortE, PortH, MAX_NB_PORT };
using PinName = uint32_t;
static constexpr PinName NC = UINT32_MAX;
static constexpr uint32_t RCC_AHB1ENR_GPIOHEN = 1U << 7;

struct RCC_TypeDef { volatile uint32_t AHB1ENR; };
extern RCC_TypeDef gpio_test_rcc;
#define RCC (&gpio_test_rcc)

// Check the clock at each configuration-register write, so the test also
// catches correct register values written before enabling the peripheral.
struct GpioRegister {
  uint32_t value = 0;
  uint32_t required_clock = 0;
  unsigned writes = 0;
  operator uint32_t() const { return value; }
  void operator=(uint32_t next) {
    assert((RCC->AHB1ENR & required_clock) == required_clock);
    value = next;
    ++writes;
  }
};

struct GPIO_TypeDef {
  GpioRegister MODER, OTYPER, OSPEEDR, PUPDR;
  volatile uint32_t IDR = 0;
  volatile uint32_t ODR = 0;
  volatile uint32_t BSRR = 0;
  volatile uint32_t AFR[2] = {};
};
extern GPIO_TypeDef* GPIOPort_list[MAX_NB_PORT];
#define get_GPIO_Port(p) ((p) < MAX_NB_PORT ? GPIOPort_list[p] : nullptr)

inline PinName digitalPinToPinName(uint32_t pin) {
  // Deliberately non-linear mapping and an alias, proving that the adapter
  // does not treat an Arduino pin number as a physical PinName.
  static constexpr PinName pins[] = {0x17, 0x0F, 0x51, NC, 0x60, 0x223,
                                     0x1001, 0x801, 0x20};
  return pin < sizeof(pins) / sizeof(pins[0]) ? pins[pin] : NC;
}

#else

namespace gpio_test {
inline uint32_t last_pin = 0;
inline uint32_t last_mode = 0;
inline uint32_t last_level = 0;
inline unsigned mode_calls = 0;
inline unsigned write_calls = 0;
inline unsigned read_calls = 0;
inline int input = 0;
}
inline void pinMode(uint32_t pin, uint32_t mode) {
  gpio_test::last_pin = pin;
  gpio_test::last_mode = mode;
  ++gpio_test::mode_calls;
}
inline void digitalWrite(uint32_t pin, uint32_t level) {
  gpio_test::last_pin = pin;
  gpio_test::last_level = level;
  ++gpio_test::write_calls;
}
inline int digitalRead(uint32_t pin) {
  gpio_test::last_pin = pin;
  ++gpio_test::read_calls;
  return gpio_test::input;
}

#endif

#endif
