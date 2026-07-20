#include "Arduino.h"
#include "config.h"
#include "ledcontrol.h"

#include <assert.h>
#include <stdio.h>

#ifndef MK61_LED_EXPECT_INACTIVE_LEVEL
  #error "Define MK61_LED_EXPECT_INACTIVE_LEVEL for the selected board"
#endif

uint32_t led_test_millis = 0;
int led_test_mode_pin = -1;
int led_test_mode = -1;
int led_test_write_pin = -1;
int led_test_write_level = -1;
unsigned led_test_write_count = 0;

static void expect_level(int level) {
  assert(led_test_write_pin == (int) PIN_LED);
  assert(led_test_write_level == level);
}

int main(void) {
  const int inactive = MK61_LED_EXPECT_INACTIVE_LEVEL;
  const int active = inactive == LOW ? HIGH : LOW;

  led::init();
  assert(led_test_mode_pin == (int) PIN_LED);
  assert(led_test_mode == OUTPUT);
  assert(led_test_write_count == 1);
  expect_level(inactive);

  led::on();
  expect_level(active);

  led::off();
  expect_level(inactive);

  led::on();
  led::blink_stop();
  expect_level(inactive);

  printf("ledcontrol_self_test: ok\n");
  return 0;
}
