#ifndef MK61_LED_CONTROL_HOST_ARDUINO_H
#define MK61_LED_CONTROL_HOST_ARDUINO_H

#include <stddef.h>
#include <stdint.h>

enum {
  PA0, PA1, PA2, PA3, PA4, PA5, PA6, PA7,
  PA8, PA9, PA10, PA11, PA12, PA13, PA14, PA15,
  PB0, PB1, PB2, PB3, PB4, PB5, PB6, PB7,
  PB8, PB9, PB10, PB11, PB12, PB13, PB14, PB15,
  PC0, PC1, PC2, PC3, PC4, PC5, PC6, PC7,
  PC8, PC9, PC10, PC11, PC12, PC13, PC14, PC15
};

static constexpr uint8_t LOW = 0;
static constexpr uint8_t HIGH = 1;
static constexpr uint8_t OUTPUT = 1;

extern uint32_t led_test_millis;
extern int led_test_mode_pin;
extern int led_test_mode;
extern int led_test_write_pin;
extern int led_test_write_level;
extern unsigned led_test_write_count;

inline uint32_t millis(void) {
  return led_test_millis;
}

inline void pinMode(uint32_t pin, uint32_t mode) {
  led_test_mode_pin = (int) pin;
  led_test_mode = (int) mode;
}

inline void digitalWrite(uint32_t pin, uint32_t level) {
  led_test_write_pin = (int) pin;
  led_test_write_level = (int) level;
  led_test_write_count++;
}

#endif
