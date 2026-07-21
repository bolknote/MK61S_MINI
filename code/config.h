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

// Старый резервный вариант хранения через EEPROM Arduino требует 8-КиБ буфер
// ОЗУ на STM32F4. Штатная конфигурация A00 хранит программы и настройки
// во внешней SPI-флеш-памяти.
#ifndef MK61_USE_ARDUINO_EEPROM_FALLBACK
  #define MK61_USE_ARDUINO_EEPROM_FALLBACK 0
#endif

// Дисплей: по умолчанию старый LCD1602. Для готовой платы Classic выбирайте
// полный профиль MK61_BOARD_CLASSIC_V2 или MK61_BOARD_CLASSIC_V3 ниже.
// Один MK61_DISPLAY_UC1609 сохранён как совместимый способ выбрать Classic V2.
//#define MK61_DISPLAY_UC1609
// CGROM LCD1602: по умолчанию японский A00. Для европейского A02 включить MK61_LCD1602_A02.
//#define MK61_LCD1602_A02

//#define CDU
//#define LK432
//#define SERIAL_OUTPUT
// Ревизию платы можно выбрать при сборке (`-DREVISION_V2`). В релизных
// сборках по умолчанию используется V3, но нельзя неявно определять V3 поверх
// явно заданного профиля V2: различаются выводы данных LCD и зуммер.
#if defined(REVISION_V2) && defined(REVISION_V3)
  #error "Select only one MK61s-mini board revision"
#endif
#if !defined(REVISION_V2) && !defined(REVISION_V3)
  #define REVISION_V3
#endif

// В Mini V2 линия LCD DB7 подключена к PC15/OSC32_OUT, поэтому включение LSE
// отбирает сигнал у LCD, а STM32duino может навсегда войти в Error_Handler,
// ожидая кварц, который нельзя использовать в этом профиле. В CDU оба вывода
// LSE также уже заняты. На остальных поддерживаемых платах можно попробовать
// запустить LSE и перейти на LSI, если запуск не удался.
#if defined(REVISION_V2) || defined(CDU)
  static constexpr bool MK61_RTC_LSE_AVAILABLE = false;
#else
  static constexpr bool MK61_RTC_LSE_AVAILABLE = true;
#endif
#define MK61s
//#define MK52s

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

// Просмотр стандартных монохромных WBMP Type 0 включён по умолчанию.
// Укажите -DMK61_ENABLE_WBMP_VIEWER=0 либо замените 1 на 0 здесь, чтобы
// исключить декодер и экранные алгоритмы из прошивки. Поддержка файлов
// .wbmp в C5/USB остаётся, поэтому отключение не делает данные недоступными.
#ifndef MK61_ENABLE_WBMP_VIEWER
  #define MK61_ENABLE_WBMP_VIEWER 1
#endif
#if MK61_ENABLE_WBMP_VIEWER != 0 && MK61_ENABLE_WBMP_VIEWER != 1
  #error "MK61_ENABLE_WBMP_VIEWER must be 0 or 1"
#endif

// Расширенная ручная настройка строк, высоты, ширины и межстрочного интервала
// графического шрифта. По умолчанию в меню остается только выбор пресета шрифта.
#ifndef MK61_ENABLE_EXTENDED_FONT_SETTINGS
  #define MK61_ENABLE_EXTENDED_FONT_SETTINGS 0
#endif

// Математический бэкенд языков (FOCAL/TinyBASIC).
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

// Делитель максимально возможной частоты CGRAM-мультиплекса. Время реальной
// перезаписи измеряется после ожидания busy flag; оставшееся время фазы
// используется для опроса клавиатуры и фоновых задач.
#if MK61_ENABLE_WBMP_VIEWER
  #ifndef MK61_IMAGE1_RATE_DIVISOR
    #define MK61_IMAGE1_RATE_DIVISOR 4
  #endif
  #if MK61_IMAGE1_RATE_DIVISOR < 1 || MK61_IMAGE1_RATE_DIVISOR > 16
    #error "MK61_IMAGE1_RATE_DIVISOR must be in range 1..16"
  #endif
#endif

#if defined(DISPLAY_UC1609) && !defined(MK61_DISPLAY_UC1609)
  #define MK61_DISPLAY_UC1609
#endif

#if defined(DISPLAY_LCD1602) && !defined(MK61_DISPLAY_LCD1602)
  #define MK61_DISPLAY_LCD1602
#endif

// Полные профили плат с UC1609. Classic V2 и V3 используют одинаковые дисплей
// и клавиатуру, но отличаются выводом буззера и полярностью LED.
//#define MK61_BOARD_CLASSIC_V2
//#define MK61_BOARD_CLASSIC_V3
//#define MK61_BOARD_40TH

#if (defined(MK61_BOARD_CLASSIC_V2) + defined(MK61_BOARD_CLASSIC_V3) + defined(MK61_BOARD_40TH)) > 1
  #error "Select only one UC1609 board profile"
#endif

#if defined(MK61_BOARD_CLASSIC_V2) || defined(MK61_BOARD_CLASSIC_V3)
  #if !defined(MK61_DISPLAY_UC1609)
    #define MK61_DISPLAY_UC1609
  #endif
  #if !defined(MK61_KEYBOARD_CLASSIC)
    #define MK61_KEYBOARD_CLASSIC
  #endif
#endif

// Профиль 40TH включает UC1609 и отдельную раскладку старой 40-клавишной версии.
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

// На mini V2/V3 линия RW подключена к PB1, поэтому после инициализации ЖКИ
// можно ждать готовность контроллера по DB7 вместо консервативных задержек.
// Остальные профили сохраняют прежний режим обмена только на запись.
#ifndef MK61_LCD1602_BUSY_FLAG
  #if defined(MK61_DISPLAY_LCD1602) && !defined(CDU) && !defined(LK432)
    #define MK61_LCD1602_BUSY_FLAG 1
  #else
    #define MK61_LCD1602_BUSY_FLAG 0
  #endif
#endif

#if MK61_LCD1602_BUSY_FLAG && (!defined(MK61_DISPLAY_LCD1602) || defined(CDU) || defined(LK432))
  #error "MK61_LCD1602_BUSY_FLAG requires a mini V2/V3 LCD1602 profile with RW"
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

// Обратная совместимость: прежние флаги UC1609 + classic-клавиатура означают
// Classic V2. Новые сборки должны задавать полный профиль явно.
#if defined(MK61_DISPLAY_UC1609) && defined(MK61_KEYBOARD_CLASSIC) && \
    !defined(MK61_BOARD_CLASSIC_V2) && !defined(MK61_BOARD_CLASSIC_V3)
  #define MK61_BOARD_CLASSIC_V2
#endif

// REVISION_V2 относится только к параллельному LCD платы mini V2 и не является
// ревизией Classic. Такая комбинация дала бы неверную распиновку буззера.
#if defined(REVISION_V2) && (defined(MK61_BOARD_CLASSIC_V2) || defined(MK61_BOARD_CLASSIC_V3) || defined(MK61_BOARD_40TH))
  #error "REVISION_V2 cannot be combined with a UC1609 board profile"
#endif

// Электрическая полярность PC13 задаётся полной платой, а не типом клавиатуры:
// mini V2/V3 и Classic V3 — active HIGH; Classic V2 и 40th — active LOW.
// Храним полярность в профиле платы, чтобы все вызовы led::on/off/blink
// использовали один и тот же аппаратно правильный уровень.
#if defined(MK61_BOARD_CLASSIC_V2) || defined(MK61_BOARD_40TH)
  static constexpr u8 MK61_STATUS_LED_ACTIVE_LOW = 1;
#else
  static constexpr u8 MK61_STATUS_LED_ACTIVE_LOW = 0;
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
  #if defined(MK61_BOARD_CLASSIC_V2)
    constexpr char MODEL[] = "MK61s-Classic-V2";
    //                       0123456789ABCDEF
    constexpr char FULL_MODEL_NAME[] = "MK61s Classic V2";
  #elif defined(MK61_BOARD_CLASSIC_V3)
    constexpr char MODEL[] = "MK61s-Classic-V3";
    //                       0123456789ABCDEF
    constexpr char FULL_MODEL_NAME[] = "MK61s Classic V3";
  #elif defined(MK61_BOARD_40TH)
    constexpr char MODEL[] = "MK61s-40th";
    //                       0123456789ABCDEF
    constexpr char FULL_MODEL_NAME[] = "MK61s-40thUC1609";
  #else
    constexpr char MODEL[] = "MK61s";
    //                       0123456789ABCDEF
    constexpr char FULL_MODEL_NAME[] = "MK61s *firmware*";
  #endif
#else
  #ifdef MK52s
    constexpr char MODEL[] = "MK52s";
    constexpr char FULL_MODEL_NAME[] = "MK52s *firmware*";
  #endif
#endif

// Отображается как "HHMMSS Mmm DD YY" (16 символов и завершающий ноль).
constexpr char FIRMWARE_VER[] = {
  __TIME__[0], __TIME__[1], __TIME__[3], __TIME__[4], __TIME__[6], __TIME__[7], ' ',
  __DATE__[0], __DATE__[1], __DATE__[2], __DATE__[3],
  (__DATE__[4] == ' ' ? '0' : __DATE__[4]), __DATE__[5], __DATE__[6],
  __DATE__[9], __DATE__[10], '\0'
};
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
 /* Описание выводов STM32F401CDU6 (BlackPill) */
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
 /* Описание выводов STM32L432, также известного как LK432, для платы расширения Arduino (Wokwi) */
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
 /* Описание выводов STM32F411CEU6 (BlackPill MK61s-mini_v2) */
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
    static constexpr u8 PIN_LED_ACTIVE_LOW = MK61_STATUS_LED_ACTIVE_LOW;
  #else
    #ifdef REVISION_V3
 /* REVISION_V3: описание выводов STM32F411CEU6 (BlackPill MK61s-mini_v3) */
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
      #ifdef MK61_BOARD_CLASSIC_V3
        static const u8 PIN_BUZZER      =   PB9;
      #else
        static const u8 PIN_BUZZER      =   PA0;
      #endif
      static const u8   PIN_LED         =   PC13;
      static constexpr u8 PIN_LED_ACTIVE_LOW = MK61_STATUS_LED_ACTIVE_LOW;
      #ifndef MK61_BOARD_CLASSIC_V3
        static const u8 PIN_OUT_PWR     =   PB9;
      #endif
      static const u8   PIN_SPIFLASH_CS =   PA4;
    #else 
 /* REVISION_V1: описание выводов STM32F411CEU6 (BlackPill MK61s-mini_v1) */
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
