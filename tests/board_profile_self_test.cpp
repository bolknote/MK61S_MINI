#include <cassert>
#include <iostream>

#include "config.h"

int main(void) {
  static_assert(PIN_SPIFLASH_CS == PA4,
                "all supported mini revisions use SPI1 NSS on PA4");
  static_assert(PIN_LCD_RS == PB2 && PIN_LCD_RW == PB1 && PIN_LCD_E == PB0,
                "LCD control pin regression");
  static_assert(PIN_LED == PC13, "status LED pin regression");

#if defined(MK61_CONFIG_EXPECT_V2)
  #if !defined(REVISION_V2) || defined(REVISION_V3)
    #error "the V2 build must select V2 only"
  #endif
  static_assert(PIN_LCD_DB4 == PA3 && PIN_LCD_DB5 == PA2 &&
                PIN_LCD_DB6 == PA1 && PIN_LCD_DB7 == PC15,
                "mini V2 LCD data pin regression");
  static_assert(PIN_BUZZER == PB10, "mini V2 buzzer pin regression");
  static_assert(PIN_LED_ACTIVE_LOW == 1,
                "mini V2 BlackPill LED must be active-low");
#else
  #if defined(REVISION_V2) || !defined(REVISION_V3)
    #error "the default build must select V3 only"
  #endif
  static_assert(PIN_LCD_DB4 == PB10 && PIN_LCD_DB5 == PA3 &&
                PIN_LCD_DB6 == PA2 && PIN_LCD_DB7 == PA1,
                "mini V3 LCD data pin regression");
  static_assert(PIN_BUZZER == PA0, "mini V3 buzzer pin regression");
  static_assert(PIN_LED_ACTIVE_LOW == 0,
                "mini V3 board LED must be active-high");
#endif

  std::cout << "board_profile_self_test: ok\n";
  return 0;
}
