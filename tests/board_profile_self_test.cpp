#include <cassert>
#include <iostream>

#include "config.h"

int main(void) {
#if defined(MK61_CONFIG_EXPECT_WBMP_DISABLED)
  static_assert(MK61_ENABLE_WBMP_VIEWER == 0,
                "the WBMP-disabled build must keep the viewer disabled");
#else
  static_assert(MK61_ENABLE_WBMP_VIEWER == 1,
                "the WBMP viewer must be enabled by default");
#endif
  static_assert(PIN_SPIFLASH_CS == PA4,
                "all supported mini revisions use SPI1 NSS on PA4");
  static_assert(PIN_LCD_RS == PB2 && PIN_LCD_RW == PB1 && PIN_LCD_E == PB0,
                "LCD control pin regression");
  static_assert(PIN_LED == PC13, "status LED pin regression");
  static_assert(sizeof(FULL_MODEL_NAME) == 17,
                "startup model name must occupy exactly 16 characters");

#if defined(MK61_CONFIG_EXPECT_V2)
  #if !defined(REVISION_V2) || defined(REVISION_V3)
    #error "the V2 build must select V2 only"
  #endif
  static_assert(PIN_LCD_DB4 == PA3 && PIN_LCD_DB5 == PA2 &&
                PIN_LCD_DB6 == PA1 && PIN_LCD_DB7 == PC15,
                "mini V2 LCD data pin regression");
  static_assert(PIN_BUZZER == PB10, "mini V2 buzzer pin regression");
  static_assert(!MK61_RTC_LSE_AVAILABLE,
                "mini V2 must not enable LSE while LCD DB7 owns PC15");
#else
  #if defined(REVISION_V2) || !defined(REVISION_V3)
    #error "the default build must select V3 only"
  #endif
  static_assert(PIN_LCD_DB4 == PB10 && PIN_LCD_DB5 == PA3 &&
                PIN_LCD_DB6 == PA2 && PIN_LCD_DB7 == PA1,
                "mini V3 LCD data pin regression");
  static_assert(MK61_RTC_LSE_AVAILABLE,
                "mini V3 leaves the LSE pins available for RTC");
#endif

#if defined(MK61_CONFIG_EXPECT_CLASSIC_V2)
  static_assert(MK61_LCD1602_BUSY_FLAG == 0,
                "UC1609 profiles must not enable the LCD1602 busy flag");
  #if !defined(MK61_BOARD_CLASSIC_V2) || !defined(MK61_DISPLAY_UC1609) || \
      !defined(MK61_KEYBOARD_CLASSIC)
    #error "the Classic V2 build must select its complete board profile"
  #endif
  static_assert(PIN_BUZZER == PA0, "Classic V2 buzzer pin regression");
  static_assert(PIN_LED_ACTIVE_LOW == 1,
                "Classic V2 LED must turn off at HIGH");
#elif defined(MK61_CONFIG_EXPECT_CLASSIC_V3)
  static_assert(MK61_LCD1602_BUSY_FLAG == 0,
                "UC1609 profiles must not enable the LCD1602 busy flag");
  #if !defined(MK61_BOARD_CLASSIC_V3) || !defined(MK61_DISPLAY_UC1609) || \
      !defined(MK61_KEYBOARD_CLASSIC)
    #error "the Classic V3 build must select its complete board profile"
  #endif
  static_assert(PIN_BUZZER == PB9, "Classic V3 buzzer pin regression");
  static_assert(PIN_LED_ACTIVE_LOW == 0,
                "Classic V3 LED must turn off at LOW");
#elif defined(MK61_CONFIG_EXPECT_V2) || defined(MK61_CONFIG_EXPECT_V3)
  static_assert(MK61_LCD1602_BUSY_FLAG == 1,
                "mini V2/V3 must use the connected LCD busy flag");
  #if defined(MK61_CONFIG_EXPECT_V3)
    static_assert(PIN_BUZZER == PA0, "mini V3 buzzer pin regression");
  #endif
  static_assert(PIN_LED_ACTIVE_LOW == 0,
                "mini V2/V3 LED must turn off at LOW");
#elif defined(MK61_CONFIG_EXPECT_40TH)
  static_assert(MK61_LCD1602_BUSY_FLAG == 0,
                "UC1609 profiles must not enable the LCD1602 busy flag");
  #if !defined(MK61_BOARD_40TH) || !defined(MK61_DISPLAY_UC1609) || \
      !defined(MK61_KEYBOARD_40TH)
    #error "the 40th build must select its complete board profile"
  #endif
  static_assert(PIN_BUZZER == PA0, "40th buzzer pin regression");
  static_assert(PIN_LED_ACTIVE_LOW == 1,
                "40th LED must turn off at HIGH");
#else
  #error "Select the expected board profile for this test"
#endif

  std::cout << "board_profile_self_test: ok\n";
  return 0;
}
