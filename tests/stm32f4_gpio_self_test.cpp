#include "stm32f4_gpio.hpp"

#include <assert.h>
#include <initializer_list>
#include <stdio.h>

#if MK61_GPIO_USES_STM32F4

RCC_TypeDef gpio_test_rcc = {};
static GPIO_TypeDef ports[MAX_NB_PORT];
GPIO_TypeDef* GPIOPort_list[MAX_NB_PORT] = {
  &ports[0], &ports[1], &ports[2], &ports[3], &ports[4], &ports[5]
};

using stm32f4_gpio::PinDescription;
static_assert(PinDescription(0x17).bit_mask() == (1U << 7), "PB7 bit");
static_assert(PinDescription(0x0F).pair_mask() == (3U << 30), "PA15 pair");
static_assert(PinDescription(0x51).clock_mask() == (1U << 7), "GPIOH clock");
static_assert(PinDescription(0x223).port_index() == PortC, "ALTx alias");
static_assert(!PinDescription(NC).valid(), "NC must be rejected");
static_assert(!PinDescription(0x1001).valid(), "internal ADC is not GPIO");

static constexpr uint32_t ORIGINAL_MODER = 0xA55AA55AU;
static constexpr uint32_t ORIGINAL_PUPDR = 0x5AA55AA5U;
static constexpr uint32_t ORIGINAL_SPEED = 0x12345678U;
static constexpr uint32_t ORIGINAL_TYPE = 0xA55AU;
static constexpr uint32_t UNRELATED_CLOCK = 1U << 28;

static void reset() {
  RCC->AHB1ENR = UNRELATED_CLOCK;
  for(uint32_t i = 0; i < MAX_NB_PORT; ++i) {
    GPIOPort_list[i] = &ports[i];
    ports[i] = {};
    const uint32_t clock = i == PortH ? RCC_AHB1ENR_GPIOHEN : 1U << i;
    for(GpioRegister* reg : {&ports[i].MODER, &ports[i].OTYPER,
                             &ports[i].OSPEEDR, &ports[i].PUPDR}) {
      reg->required_clock = clock;
    }
    ports[i].MODER.value = ORIGINAL_MODER;
    ports[i].PUPDR.value = ORIGINAL_PUPDR;
    ports[i].OSPEEDR.value = ORIGINAL_SPEED;
    ports[i].OTYPER.value = ORIGINAL_TYPE;
    ports[i].ODR = 0x1234;
    ports[i].BSRR = 0x5678;
    ports[i].AFR[0] = 0x12345678;
    ports[i].AFR[1] = 0xABCDEF01;
  }
}

static void expect_unchanged(const GPIO_TypeDef& port) {
  assert(port.MODER.value == ORIGINAL_MODER && port.MODER.writes == 0);
  assert(port.PUPDR.value == ORIGINAL_PUPDR && port.PUPDR.writes == 0);
  assert(port.OSPEEDR.value == ORIGINAL_SPEED && port.OSPEEDR.writes == 0);
  assert(port.OTYPER.value == ORIGINAL_TYPE && port.OTYPER.writes == 0);
  assert(port.ODR == 0x1234 && port.BSRR == 0x5678);
  assert(port.AFR[0] == 0x12345678 && port.AFR[1] == 0xABCDEF01);
}

static void test_configuration() {
  struct Mode { uint32_t api, direction, pull; bool output, open_drain; };
  const Mode modes[] = {
    {INPUT, 0, 0, false, false}, {INPUT_PULLUP, 0, 1, false, false},
    {INPUT_PULLDOWN, 0, 2, false, false}, {INPUT_ANALOG, 3, 0, false, false},
    {OUTPUT, 1, 0, true, false}, {OUTPUT_OPEN_DRAIN, 1, 0, true, true}
  };
  const uint32_t digital_pins[] = {0, 1, 2, 5, 8};
  for(uint32_t digital_pin : digital_pins) {
    const PinDescription description(digitalPinToPinName(digital_pin));
    for(const Mode& mode : modes) {
      reset();
      stm32f4_gpio::configure(digital_pin, mode.api);
      const GPIO_TypeDef& port = ports[description.port_index()];
      const uint32_t mask = description.pair_mask();
      const uint32_t shift = description.shift();
      assert(RCC->AHB1ENR == (UNRELATED_CLOCK | description.clock_mask()));
      assert(port.MODER.value == ((ORIGINAL_MODER & ~mask) | (mode.direction << shift)));
      assert(port.PUPDR.value == ((ORIGINAL_PUPDR & ~mask) | (mode.pull << shift)));
      assert(port.OSPEEDR.value == ((ORIGINAL_SPEED & ~mask) | mask));
      const uint32_t type = mode.output ?
        ((ORIGINAL_TYPE & ~description.bit_mask()) |
          (mode.open_drain ? description.bit_mask() : 0U)) : ORIGINAL_TYPE;
      assert(port.OTYPER.value == type);
      assert(port.OTYPER.writes == (mode.output ? 1U : 0U));
      assert(port.MODER.writes == 1 && port.PUPDR.writes == 1 && port.OSPEEDR.writes == 1);
      assert(port.ODR == 0x1234 && port.BSRR == 0x5678);
      assert(port.AFR[0] == 0x12345678 && port.AFR[1] == 0xABCDEF01);
      for(uint32_t other = 0; other < MAX_NB_PORT; ++other) {
        if(other != description.port_index()) expect_unchanged(ports[other]);
      }
    }
  }
}

static void test_data_access() {
  reset();
  stm32f4_gpio::configure(0, OUTPUT);
  stm32f4_gpio::write(0, HIGH);
  assert(ports[PortB].BSRR == (1U << 7));
  stm32f4_gpio::write(0, 73); // Arduino accepts every nonzero level as HIGH.
  assert(ports[PortB].BSRR == (1U << 7));
  stm32f4_gpio::write(0, LOW);
  assert(ports[PortB].BSRR == (1U << 23));
  assert(ports[PortB].ODR == 0x1234); // BSRR, never an ODR read/modify/write.
  ports[PortB].IDR = 1U << 6;
  assert(stm32f4_gpio::read(0) == LOW);
  ports[PortB].IDR |= 1U << 7;
  assert(stm32f4_gpio::read(0) == HIGH);
  stm32f4_gpio::configure(1, OUTPUT);
  stm32f4_gpio::write(1, LOW);
  assert(ports[PortA].BSRR == (1U << 31));
}

static void test_invalid_requests() {
  for(uint32_t pin : {3U, 4U, 6U, 7U, 123U, UINT32_MAX}) {
    reset();
    stm32f4_gpio::configure(pin, OUTPUT);
    stm32f4_gpio::write(pin, HIGH);
    assert(stm32f4_gpio::read(pin) == LOW);
    assert(RCC->AHB1ENR == UNRELATED_CLOCK);
    for(const GPIO_TypeDef& port : ports) expect_unchanged(port);
  }
  reset();
  stm32f4_gpio::configure(0, 123);
  assert(RCC->AHB1ENR == UNRELATED_CLOCK);
  for(const GPIO_TypeDef& port : ports) expect_unchanged(port);
  GPIOPort_list[PortB] = nullptr;
  stm32f4_gpio::configure(0, OUTPUT);
  stm32f4_gpio::write(0, HIGH);
  assert(stm32f4_gpio::read(0) == LOW);
  assert(RCC->AHB1ENR == UNRELATED_CLOCK);
  for(const GPIO_TypeDef& port : ports) expect_unchanged(port);
}

#endif

int main() {
#if MK61_GPIO_USES_STM32F4
  test_configuration();
  test_data_access();
  test_invalid_requests();
#else
  stm32f4_gpio::configure(123, OUTPUT_OPEN_DRAIN);
  assert(gpio_test::mode_calls == 1 && gpio_test::last_pin == 123);
  assert(gpio_test::last_mode == OUTPUT_OPEN_DRAIN);
  stm32f4_gpio::write(31, HIGH);
  assert(gpio_test::write_calls == 1 && gpio_test::last_pin == 31);
  assert(gpio_test::last_level == HIGH);
  gpio_test::input = HIGH;
  assert(stm32f4_gpio::read(7) == HIGH);
  assert(gpio_test::read_calls == 1 && gpio_test::last_pin == 7);
#endif
  puts("stm32f4_gpio_self_test: ok");
}
