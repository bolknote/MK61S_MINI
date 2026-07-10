#ifndef CONFIG
#define CONFIG

#include "Arduino.h"
#include "rust_types.h"

//#define DEBUG_CORE61        // Полная отладочная информация по ядру mk61s (почти не слушает клавиатуру)
//#define DEBUG_TRACE         // Отладочная трассировочная информация по значению
//#define DEBUG_MINI          // Отладочная информация по оболочке MK61S-MINI
//#define DEBUG_SPIFLASH      // Отладочная информация по обработке внешней флеш памяти
//#define DEBUG_DISASMBLER    // Отладочная информация по встроенному дисассемблеру МК61 инструкций
//#define DEBUG_KBD           // Отладочная информация по клавиатурному драйверу
//#define DEBUG_MENU          // Отладочная информация по системе меню
//#define DEBUG_LIBRARY       // Отладочная информация по библиотеке программ МК61
//#define DEBUG_MK61E         // Отладочная информация расширяющая представление вывода терминала по МК61
//#define DEBUG_PARSE         // Отладочная информация по парсеру ассемблера
// Расширение памяти программы 105/112 теперь переключается из меню.
//#define DEBUG_MEASURE       // Вывод времени исполнения от С/П до С/П для вычисления производительности ядра
//#define DEBUG_RUN_STOP      // Отладочный вывод по расширению команды С/П
//#define MK61_EXTENDED
//#define B3_34
#define TERMINAL
#define SPI_FLASH
//#define DEBUG
//#define DEBUG_M61

// Старый fallback хранения через Arduino EEPROM тянет 8 КБ RAM-буфер на STM32F4.
// Штатная A00-конфигурация хранит программы и настройки во внешней SPI flash.
#ifndef MK61_USE_ARDUINO_EEPROM_FALLBACK
  #define MK61_USE_ARDUINO_EEPROM_FALLBACK 0
#endif

// Дисплей: по умолчанию старый LCD1602. Для ERM19264/UC1609 включить MK61_DISPLAY_UC1609.
//#define MK61_DISPLAY_UC1609
// CGROM LCD1602: по умолчанию японский A00. Для европейского A02 включить MK61_LCD1602_A02.
//#define MK61_LCD1602_A02

//#define CDU
//#define LK432
//#define SERIAL_OUTPUT
#define REVISION_V3
//#define REVISION_V2
#define MK61s
//#define MK52s

// Встроенный "большой" БЕЙСИК отключен по умолчанию: он заметно увеличивает
// расход RAM. Поставьте 1, чтобы вернуть его редактор, рантайм, меню и
// привязку к шагам МК-61 в прошивку.
#ifndef MK61_ENABLE_BASIC
  #define MK61_ENABLE_BASIC 0
#endif

// Встроенный FOCAL включен по умолчанию. Поставьте 0, чтобы убрать его
// редактор, рантайм и меню из прошивки.
#ifndef MK61_ENABLE_FOCAL
  #define MK61_ENABLE_FOCAL 1
#endif

// TinyBASIC включен по умолчанию. Поставьте 0, чтобы убрать его
// редактор, рантайм и меню из прошивки.
#ifndef MK61_ENABLE_TINYBASIC
  #define MK61_ENABLE_TINYBASIC 1
#endif

// Расширенная ручная настройка строк, высоты, ширины и межстрочного интервала
// графического шрифта. По умолчанию в меню остается только выбор пресета шрифта.
#ifndef MK61_ENABLE_EXTENDED_FONT_SETTINGS
  #define MK61_ENABLE_EXTENDED_FONT_SETTINGS 0
#endif

// Математический бэкенд языков (FOCAL/BASIC/TinyBASIC).
//  LIBM (умолчание) — трансцендентные функции через <math.h>.
//  CORE             — вычисление на ядре МК-61; убирает libm из прошивки
//                     ценой ~8 значащих цифр и меньшей скорости.
#define MK61_MATH_BACKEND_LIBM 0
#define MK61_MATH_BACKEND_CORE 1
#ifndef MK61_MATH_BACKEND
  #define MK61_MATH_BACKEND MK61_MATH_BACKEND_LIBM
#endif

// Короткое нажатие [USER] открывает Проводник. Поставьте 0, чтобы оставить
// [USER] только для удержания стека и функций режима ПРГ.
#ifndef MK61_USER_EXPLORER_SHORTCUT
  #define MK61_USER_EXPLORER_SHORTCUT 1
#endif

#if defined(DISPLAY_UC1609) && !defined(MK61_DISPLAY_UC1609)
  #define MK61_DISPLAY_UC1609
#endif

#if defined(DISPLAY_LCD1602) && !defined(MK61_DISPLAY_LCD1602)
  #define MK61_DISPLAY_LCD1602
#endif

// MK61s 40th profile: UC1609 display with the keyboard wiring/layout used by
// the older 40-key firmware snapshot.
#if defined(MK61_BOARD_40TH)
  #if !defined(MK61_DISPLAY_UC1609)
    #define MK61_DISPLAY_UC1609
  #endif
  #if !defined(MK61_KEYBOARD_40TH)
    #define MK61_KEYBOARD_40TH
  #endif
#endif

#if !defined(MK61_DISPLAY_UC1609)
  #define MK61_DISPLAY_LCD1602
#endif

#if defined(DISPLAY_LCD1602_A00) && !defined(MK61_LCD1602_A00)
  #define MK61_LCD1602_A00
#endif

#if defined(DISPLAY_LCD1602_A02) && !defined(MK61_LCD1602_A02)
  #define MK61_LCD1602_A02
#endif

#if defined(MK61_LCD1602_A00) && defined(MK61_LCD1602_A02)
  #error "Select only one LCD1602 CGROM variant"
#endif

#if defined(MK61_DISPLAY_LCD1602) && !defined(MK61_LCD1602_A00) && !defined(MK61_LCD1602_A02)
  #define MK61_LCD1602_A00
#endif

// Клавиатура: у classic-платформы с UC1609 другая физическая матрица и коды.
// Если вариант не задан явно, LCD1602 остается mk61s-mini, UC1609 выбирает classic.
#if defined(MK61_DISPLAY_UC1609) && !defined(MK61_KEYBOARD_MINI) && !defined(MK61_KEYBOARD_CLASSIC) && !defined(MK61_KEYBOARD_40TH)
  #define MK61_KEYBOARD_CLASSIC
#endif

#if !defined(MK61_KEYBOARD_CLASSIC) && !defined(MK61_KEYBOARD_MINI) && !defined(MK61_KEYBOARD_40TH)
  #define MK61_KEYBOARD_MINI
#endif

#if (defined(MK61_KEYBOARD_CLASSIC) + defined(MK61_KEYBOARD_MINI) + defined(MK61_KEYBOARD_40TH)) > 1
  #error "Select only one keyboard layout"
#endif

#define IS_CORTEX_M4() (__ARM_ARCH == 7)
//defined(__ARM_ARCH_7EM__)
//defined(__ARM_FEATURE_SIMD32)

#if defined(TERMINAL) || defined(DEBUG)
 //#warning Serial module included!
#endif

// Терминал использует Serial независимо от включенных отладочных категорий.
// Раньше SERIAL_OUTPUT появлялся только как побочный эффект DEBUG_* и сборка
// ломалась при отключении отладки с оставленным TERMINAL.
#if defined(TERMINAL) && !defined(SERIAL_OUTPUT)
  #define SERIAL_OUTPUT
#endif

#ifdef DEBUG_TRACE
  constexpr bool DBG_TRACE = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_TRACE = false;
#endif

#ifdef DEBUG_PARSE
  constexpr bool DBG_PARSE = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_PARSE = false;
#endif

#ifdef DEBUG_MEASURE
  constexpr bool DBG_MEASURE = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_MEASURE = false;
#endif

#ifdef DEBUG_MINI
  constexpr bool DBG_MINI = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_MINI = false;
#endif

#ifdef DEBUG_SPIFLASH
  constexpr bool DBG_SPIROM = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_SPIROM = false;
#endif

#ifdef DEBUG_DISASMBLER
  constexpr bool DBG_DISASM = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_DISASM = false;
#endif

#ifdef DEBUG_KBD
  constexpr bool DBG_KBD = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_KBD = false;
#endif

#ifdef DEBUG_MENU
  constexpr bool DBG_MENU = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_MENU = false;
#endif

#ifdef DEBUG_CORE61
  constexpr bool DBG_CORE61 = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_CORE61 = false;
#endif

#ifdef DEBUG_LIBRARY
  constexpr bool DBG_LIB61 = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_LIB61 = false;
#endif

#ifdef DEBUG_MK61E
  constexpr bool DBG_MK61E = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_MK61E = false;
#endif

#ifdef DEBUG_RUN_STOP
  constexpr bool DBG_EXT_RUN = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_EXT_RUN = false;
#endif

#ifdef MK61_FOCAL_TRACE
  constexpr bool DBG_FOCAL = true;
  #define SERIAL_OUTPUT
#else
  constexpr bool DBG_FOCAL = false;
#endif

#ifdef ARDUINO_BLACKPILL_F411CE
  const char chip_name[] = "STM32F411CE";
  const char mem_text[] = "RAM:128 ROM:512";
#else
  #ifdef ARDUINO_BLACKPILL_F401CE
    const char chip_name[] = "STM32F401CE";
    const char mem_text[] = "RAM:96 ROM:512";
  #else
    #ifdef ARDUINO_BLACKPILL_F401CC
      const char chip_name[] = "STM32F401CC";
      const char mem_text[] = "RAM:64 ROM:256";
    #else
      #ifdef ARDUINO_GENERIC_F401CDUX
        const char chip_name[] = "STM32F401CD";
        const char mem_text[] = "RAM:96 ROM:384";
      #else
        #ifdef ARDUINO_GENERIC_F411CCUX
          const char chip_name[] = "STM32F411CC";
          const char mem_text[] = "RAM:128 ROM:256";
        #else
          #ifdef ARDUINO_GENERIC_F401CBYX
            const char chip_name[] = "STM32F401CB";
            const char mem_text[] = "RAM:64 ROM:128";
          #else
            const char chip_name[] = "unknown chip";
            const char mem_text[] = "unknown memory";
          #endif
        #endif
      #endif
    #endif
  #endif
#endif

#ifdef MK61s
    #ifdef MK61_BOARD_40TH
      const char MODEL[] = "MK61s-40th";
      //                       0123456789ABCDEF
      const char FULL_MODEL_NAME[] = "MK61s-40thUC1609";
    #else
      const char MODEL[] = "MK61s";
      //                       0123456789ABCDEF
      const char FULL_MODEL_NAME[] = "MK61s *firmware*";
    #endif
  #else 
    #ifdef MK52s
      const char MODEL[] = "MK52s";
      const char FULL_MODEL_NAME[] = "MK52s *firmware*";
    #endif
#endif

#define FIRMWARE_VER (char const[]) {__TIME__[0], __TIME__[1],__TIME__[3],__TIME__[4],__TIME__[6],__TIME__[7],' ',__DATE__[0], __DATE__[1], __DATE__[2], __DATE__[3], (__DATE__[4] == ' ' ?  '0' : __DATE__[4]), __DATE__[5], __DATE__[6], __DATE__[9], __DATE__[10], __DATE__[11]}
class class_calc_config {
  public:
    bool disassm;
    bool output_IP;
    class_calc_config(void) : disassm(false), output_IP(false) {}
};

namespace cfg {

static constexpr isize  CLASSIC_MK61_QUANTS    =    72500;   // Константна замедления ядра mk61s в классичесокм режиме
static constexpr usize  TURBO_MK61_BATCH_STEPS =       16;   // Сколько шагов ядра делать за один проход RUN-обвязки в режиме TURBO
static constexpr t_time_ms TURBO_LCD_UPDATE_MS =      120;   // Минимальная пауза между обновлениями LCD в TURBO RUN
static constexpr usize  TURBO_SERIAL_POLL_LOOPS =       4;   // Как часто опрашивать терминал в TURBO RUN

}

// Конфигурация подключения микроконтроллера на макетной или печтаной плате 
#ifdef CDU
 /* Описание ног для STM32F401CDU6 aka BlackPill */
  static const u8   PIN_LCD_RS      =   PC14;
  static const u8   PIN_LCD_E       =   PC15;
  static const u8   PIN_LCD_DB4     =   PB0;
  static const u8   PIN_LCD_DB5     =   PB1;
  static const u8   PIN_LCD_DB6     =   PB2;
  static const u8   PIN_LCD_DB7     =   PB3;
  static const u8   PIN_KBD_COL0    =   PA0;
  static const u8   PIN_KBD_COL1    =   PA1;
  static const u8   PIN_KBD_COL2    =   PA2;
  static const u8   PIN_KBD_COL3    =   PA3;
  static const u8   PIN_KBD_COL4    =   PA4;
  static const u8   PIN_KBD_COL5    =   PA5;
  static const u8   PIN_KBD_COL6    =   PA6;
  static const u8   PIN_KBD_COL7    =   PA7;
  static const u8   PIN_KBD_ROW4    =   PB8;
  static const u8   PIN_KBD_ROW3    =   PB7;
  static const u8   PIN_KBD_ROW2    =   PB6;
  static const u8   PIN_KBD_ROW1    =   PB5;
  static const u8   PIN_KBD_ROW0    =   PB4;
  static const u8   PIN_SPIFLASH_CS =   PA4;
#else
 #ifdef LK432
 /* Описание ног для STM32L432 aka LK432 in Arduino shield (Wokwi)*/
  static const u8   PIN_LCD_RS      =   D12;
  static const u8   PIN_LCD_E       =   D11;
  static const u8   PIN_LCD_DB4     =   D10;
  static const u8   PIN_LCD_DB5     =   D9;
  static const u8   PIN_LCD_DB6     =   D8;
  static const u8   PIN_LCD_DB7     =   D8;
  static const u8   PIN_KBD_COL0    =   A0;
  static const u8   PIN_KBD_COL1    =   A1;
  static const u8   PIN_KBD_COL2    =   A2;
  static const u8   PIN_KBD_COL3    =   A3;
  static const u8   PIN_KBD_COL4    =   A4;
  static const u8   PIN_KBD_COL5    =   A5;
  static const u8   PIN_KBD_COL6    =   A6;
  static const u8   PIN_KBD_COL7    =   A7;
  static const u8   PIN_KBD_ROW4    =   D2;
  static const u8   PIN_KBD_ROW3    =   D4;
  static const u8   PIN_KBD_ROW2    =   D5;
  static const u8   PIN_KBD_ROW1    =   D6;
  static const u8   PIN_KBD_ROW0    =   D13;
  static const u8   PIN_SPIFLASH_CS =   PA4;
 #else
  #ifdef REVISION_V2
 /* Описание ног для STM32F411CEU6 aka BlackPill MK61s-mini_v2*/
    static const u8   PIN_LCD_RS      =   PB2;
    static const u8   PIN_LCD_RW      =   PB1;
    static const u8   PIN_LCD_E       =   PB0;
    static const u8   PIN_LCD_DB4     =   PA3;
    static const u8   PIN_LCD_DB5     =   PA2;
    static const u8   PIN_LCD_DB6     =   PA1;
    static const u8   PIN_LCD_DB7     =   PC15;
    static const u8   PIN_KBD_COL0    =   PB12;
    static const u8   PIN_KBD_COL1    =   PB13;
    static const u8   PIN_KBD_COL2    =   PB14;
    static const u8   PIN_KBD_COL3    =   PB15;
    static const u8   PIN_KBD_COL4    =   PA8;
    static const u8   PIN_KBD_COL5    =   PA9;
    static const u8   PIN_KBD_COL6    =   PA10;
    static const u8   PIN_KBD_COL7    =   PA15;
    static const u8   PIN_KBD_ROW4    =   PB8;
    static const u8   PIN_KBD_ROW3    =   PB7;
    static const u8   PIN_KBD_ROW2    =   PB6;
    static const u8   PIN_KBD_ROW1    =   PB5;
    static const u8   PIN_KBD_ROW0    =   PB4;
    static const u8   PIN_J2          =   PB3;
    static const u8   PIN_BUZZER      =   PB10;
    static const u8   PIN_SPIFLASH_CS =   PA4;
    static const u8   PIN_LED         =   PC13;
    static constexpr u8 PIN_LED_ACTIVE_LOW = 1;
  #else
    #ifdef REVISION_V3
 /* REVISION_V3 Описание ног для STM32F411CEU6 aka BlackPill MK61s-mini_v3*/
      static const u8   PIN_LCD_RS      =   PB2;
      static const u8   PIN_LCD_E       =   PB0;
      static const u8   PIN_LCD_RW      =   PB1;
      static const u8   PIN_LCD_DB4     =   PB10;
      static const u8   PIN_LCD_DB5     =   PA3;
      static const u8   PIN_LCD_DB6     =   PA2;
      static const u8   PIN_LCD_DB7     =   PA1;
      static const u8   PIN_KBD_COL0    =   PB12;
      static const u8   PIN_KBD_COL1    =   PB13;
      static const u8   PIN_KBD_COL2    =   PB14;
      static const u8   PIN_KBD_COL3    =   PB15;
      static const u8   PIN_KBD_COL4    =   PA8;
      static const u8   PIN_KBD_COL5    =   PA9;
      static const u8   PIN_KBD_COL6    =   PA10;
      static const u8   PIN_KBD_COL7    =   PA15;
      static const u8   PIN_KBD_ROW4    =   PB8;
      static const u8   PIN_KBD_ROW3    =   PB7;
      static const u8   PIN_KBD_ROW2    =   PB6;
      static const u8   PIN_KBD_ROW1    =   PB5;
      static const u8   PIN_KBD_ROW0    =   PB4;
      static const u8   PIN_BUZZER      =   PA0;
      static const u8   PIN_LED         =   PC13;
      static constexpr u8 PIN_LED_ACTIVE_LOW = 1;
      static const u8   PIN_OUT_PWR     =   PB9;
      static const u8   PIN_SPIFLASH_CS =   PA4;
    #else 
 /* REVISION_V1 Описание ног для STM32F411CEU6 aka BlackPill MK61s-mini_v1*/
      static constexpr usize   PIN_LCD_RS      =   PB1;
      static constexpr usize   PIN_LCD_E       =   PB0;
      static constexpr usize   PIN_LCD_DB4     =   PA3;
      static constexpr usize   PIN_LCD_DB5     =   PA2;
      static constexpr usize   PIN_LCD_DB6     =   PA1;
      static constexpr usize   PIN_LCD_DB7     =   PA0;
      static constexpr usize   PIN_KBD_COL0    =   PB12;
      static constexpr usize   PIN_KBD_COL1    =   PB13;
      static constexpr usize   PIN_KBD_COL2    =   PB14;
      static constexpr usize   PIN_KBD_COL3    =   PB15;
      static constexpr usize   PIN_KBD_COL4    =   PA8;
      static constexpr usize   PIN_KBD_COL5    =   PA11;
      static constexpr usize   PIN_KBD_COL6    =   PA12;
      static constexpr usize   PIN_KBD_COL7    =   PA15;
      static constexpr usize   PIN_KBD_ROW4    =   PB8;
      static constexpr usize   PIN_KBD_ROW3    =   PB7;
      static constexpr usize   PIN_KBD_ROW2    =   PB6;
      static constexpr usize   PIN_KBD_ROW1    =   PB5;
      static constexpr usize   PIN_KBD_ROW0    =   PB4;
      static constexpr usize   PIN_SPIFLASH_CS =   PA4;
      static constexpr usize   PIN_BUZZER      =   PB10;
      static constexpr usize   PIN_LED         =   PC13;
      static constexpr u8      PIN_LED_ACTIVE_LOW = 1;
    #endif
  #endif
 #endif
#endif

#ifdef MK61_DISPLAY_UC1609
  static constexpr u8 PIN_GLCD_CD = PA2;
  static constexpr u8 PIN_GLCD_RST = PA3;
  static constexpr u8 PIN_GLCD_CS = PA1;
  static constexpr u8 GLCD_UC1609_BIAS = 0x1F;
  static constexpr u8 GLCD_UC1609_ADDRESS_SET = 0x02;
#endif

#endif
