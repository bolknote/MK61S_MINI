#include <cassert>
#include <iostream>

#include "config.h"

int main(void) {
#if defined(MK61_CONFIG_EXPECT_NATIVE_HOT_PATHS)
  static_assert(MK61_CORE_NATIVE_HOT_PATHS == 1,
                "size-optimised F411 must enable native core hot paths");
#elif defined(MK61_CONFIG_EXPECT_GENERIC_HOT_PATHS)
  static_assert(MK61_CORE_NATIVE_HOT_PATHS == 0,
                "this profile must keep the generic core decoder");
#endif
#if defined(MK61_CONFIG_EXPECT_WBMP_DISABLED)
  static_assert(MK61_ENABLE_WBMP_VIEWER == 0,
                "the WBMP-disabled build must keep the viewer disabled");
#elif defined(MK61_CONFIG_EXPECT_WBMP_ENABLED)
  static_assert(MK61_ENABLE_WBMP_VIEWER == 1,
                "the selected bitmap build must enable WBMP");
#elif defined(MK61_CONFIG_EXPECT_MARKDOWN_DISABLED) && \
      MK61_HAS_FULLSCREEN_BITMAP
  static_assert(MK61_ENABLE_WBMP_VIEWER == 1,
                "a fullscreen bitmap target without Markdown must enable WBMP by default");
#else
  static_assert(MK61_ENABLE_WBMP_VIEWER == 0,
                "Markdown or a non-graphical build must default WBMP off");
#endif
  static_assert(MK61_ENABLE_MARKDOWN_VIEWER ==
#if defined(MK61_CONFIG_EXPECT_MARKDOWN_DISABLED)
                0,
#else
                1,
#endif
                "Markdown must be enabled by default");
  static_assert(MK61_MARKDOWN_USES_WBMP ==
                    (MK61_ENABLE_MARKDOWN_VIEWER &&
                     MK61_HAS_FULLSCREEN_BITMAP),
                "Markdown must own WBMP on every fullscreen bitmap target");
  static_assert(MK61_HAS_FULLSCREEN_BITMAP >= MK61_HAS_COMPILED_GRAPHICS,
                "every full graphics backend must accept fullscreen bitmaps");
  static_assert(MK61_STANDALONE_WBMP_VIEWER_ENABLED ==
                    (MK61_ENABLE_WBMP_VIEWER &&
                     !MK61_MARKDOWN_USES_WBMP),
                "only graphical Markdown may absorb the WBMP viewer");
  static_assert(MK61_ENABLE_CHIP8 ==
#if defined(MK61_CONFIG_EXPECT_CHIP8)
                1,
#else
                0,
#endif
                "CHIP-8 must remain opt-in");
#if defined(MK61_CONFIG_EXPECT_GRAPHICS)
  static_assert(MK61_HAS_COMPILED_GRAPHICS == 1,
                "USB Screen or UC1609 must provide compiled graphics");
#endif
#if defined(MK61_CONFIG_EXPECT_FULLSCREEN_BITMAP)
  static_assert(MK61_HAS_FULLSCREEN_BITMAP == 1,
                "the selected display must accept fullscreen bitmaps");
#endif

#if defined(MK61_CONFIG_EXPECT_LOADABLE_MODULES)
  static_assert(MK61_ENABLE_LOADABLE_MODULES == 1,
                "the F401CC profile must enable loadable modules");
  static_assert(MK61_FOCAL_IS_LOADABLE && MK61_TINYBASIC_IS_LOADABLE,
                "enabled language runtimes must become modules");
  static_assert(MK61_WBMP_VIEWER_IS_LOADABLE ==
                    MK61_STANDALONE_WBMP_VIEWER_ENABLED &&
                MK61_MARKDOWN_VIEWER_IS_LOADABLE ==
                    MK61_ENABLE_MARKDOWN_VIEWER &&
                MK61_CHIP8_IS_LOADABLE == MK61_ENABLE_CHIP8,
                "enabled graphical runtimes must become modules");
  static_assert(MK61_ANY_LOADABLE_MODULE,
                "the loader must remain present while a module is enabled");
#elif defined(MK61_CONFIG_EXPECT_NO_MODULE_ARTIFACTS)
  static_assert(MK61_ENABLE_LOADABLE_MODULES == 1,
                "this case tests an enabled module framework");
  static_assert(!MK61_FOCAL_IS_LOADABLE && !MK61_TINYBASIC_IS_LOADABLE &&
                !MK61_WBMP_VIEWER_IS_LOADABLE &&
                !MK61_MARKDOWN_VIEWER_IS_LOADABLE &&
                !MK61_CHIP8_IS_LOADABLE,
                "disabled features must not leave system APP artifacts");
  static_assert(MK61_ANY_LOADABLE_MODULE,
                "generic APP runtime must not depend on system APP keys");
#elif defined(MK61_CONFIG_EXPECT_MODULES_DISABLED)
  static_assert(MK61_ENABLE_LOADABLE_MODULES == 0,
                "the explicit module override must win");
  static_assert(MK61_FOCAL_IS_BUILTIN && MK61_TINYBASIC_IS_BUILTIN,
                "enabled language features must stay built in");
  static_assert(MK61_WBMP_VIEWER_IS_BUILTIN ==
                    MK61_STANDALONE_WBMP_VIEWER_ENABLED &&
                MK61_MARKDOWN_VIEWER_IS_BUILTIN ==
                    MK61_ENABLE_MARKDOWN_VIEWER &&
                MK61_CHIP8_IS_BUILTIN == MK61_ENABLE_CHIP8,
                "enabled graphical features must stay built in");
  static_assert(MK61_IMAGE1_VIEWER_IS_BUILTIN ==
                    (MK61_WBMP_VIEWER_IS_BUILTIN ||
                     (MK61_MARKDOWN_VIEWER_IS_BUILTIN &&
                      MK61_MARKDOWN_USES_WBMP)),
                "Markdown must provide the built-in I1 viewer");
#else
  static_assert(MK61_ENABLE_LOADABLE_MODULES == 0,
                "non-F401 profiles must keep modules disabled by default");
#endif
  static_assert(PIN_SPIFLASH_CS == PA4,
                "all supported mini revisions use SPI1 NSS on PA4");
  static_assert(PIN_LCD_RS == PB2 && PIN_LCD_RW == PB1 && PIN_LCD_E == PB0,
                "LCD control pin regression");
  static_assert(PIN_LED == PC13, "status LED pin regression");
  static_assert(sizeof(FULL_MODEL_NAME) == 17,
                "startup model name must occupy exactly 16 characters");

#if defined(MK61_DISPLAY_UC1609)
  static_assert(MK61_ENABLE_SPI1_ARBITER == 0 && MK61_ENABLE_SPI1_DMA == 0,
                "physical UC1609 must retain polling until hardware acceptance");
#else
  static_assert(MK61_ENABLE_SPI1_ARBITER == 1 && MK61_ENABLE_SPI1_DMA == 1,
                "mini must enable the accepted SPI1 arbiter and DMA path");
#endif

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
#elif defined(MK61_CONFIG_EXPECT_WS0010)
  static_assert(MK61_LCD1602_BUSY_FLAG == 1,
                "mini V3 WS0010 must perform the datasheet BF check");
  #if !defined(MK61_OLED1602_WS0010) || \
      defined(MK61_LCD1602_A00) || defined(MK61_LCD1602_A02)
    #error "the WS0010 build must select its own character-display profile"
  #endif
  #if defined(REVISION_V2) || !defined(REVISION_V3)
    #error "the accepted WS0010 profile currently targets mini V3"
  #endif
  static_assert(PIN_BUZZER == PA0, "mini V3 buzzer regression");
  static_assert(PIN_LCD_DB4 == PB10 && PIN_LCD_DB5 == PA3 &&
                PIN_LCD_DB6 == PA2 && PIN_LCD_DB7 == PA1,
                "WS0010 BF qualification depends on the four V3 FT pins");
  static_assert(PIN_LED_ACTIVE_LOW == 0,
                "mini V3 LED must turn off at LOW");
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
