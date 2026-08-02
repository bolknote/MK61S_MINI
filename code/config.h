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

// DWT CYCCNT-профилировщик не собирает данные до команды `prof start`.
// Значение 0 полностью удаляет точки измерения и терминальную команду.
#ifndef MK61_ENABLE_DWT_PROFILER
  #define MK61_ENABLE_DWT_PROFILER 1
#endif
#if MK61_ENABLE_DWT_PROFILER != 0 && MK61_ENABLE_DWT_PROFILER != 1
  #error "MK61_ENABLE_DWT_PROFILER must be 0 or 1"
#endif

// Аппаратные faults сохраняют компактную запись в .noinit и перезагружают
// MCU. Преднамеренные faults никогда не входят в release по умолчанию и
// включаются отдельным флагом только для стендовой проверки.
#ifndef MK61_ENABLE_CRASH_DUMP
  #define MK61_ENABLE_CRASH_DUMP 1
#endif
#if MK61_ENABLE_CRASH_DUMP != 0 && MK61_ENABLE_CRASH_DUMP != 1
  #error "MK61_ENABLE_CRASH_DUMP must be 0 or 1"
#endif
#ifndef MK61_ENABLE_FAULT_INJECTION
  #define MK61_ENABLE_FAULT_INJECTION 0
#endif
#if MK61_ENABLE_FAULT_INJECTION != 0 && MK61_ENABLE_FAULT_INJECTION != 1
  #error "MK61_ENABLE_FAULT_INJECTION must be 0 or 1"
#endif

// Cortex-M4 MPU guards catch null access, stack/heap collision and (where no
// System APP executes from SRAM) accidental code execution from data memory.
#ifndef MK61_ENABLE_MPU_GUARDS
  #define MK61_ENABLE_MPU_GUARDS 1
#endif
#if MK61_ENABLE_MPU_GUARDS != 0 && MK61_ENABLE_MPU_GUARDS != 1
  #error "MK61_ENABLE_MPU_GUARDS must be 0 or 1"
#endif
#ifndef MK61_ENABLE_MPU_TEST
  #define MK61_ENABLE_MPU_TEST 0
#endif
#if MK61_ENABLE_MPU_TEST != 0 && MK61_ENABLE_MPU_TEST != 1
  #error "MK61_ENABLE_MPU_TEST must be 0 or 1"
#endif

// IWDG стартует только в конце setup и кормится после завершённого foreground
// service epoch. Стендовые starvation/hang действия отсутствуют в release.
#ifndef MK61_ENABLE_INDEPENDENT_WATCHDOG
  #define MK61_ENABLE_INDEPENDENT_WATCHDOG 1
#endif
#if MK61_ENABLE_INDEPENDENT_WATCHDOG != 0 && \
    MK61_ENABLE_INDEPENDENT_WATCHDOG != 1
  #error "MK61_ENABLE_INDEPENDENT_WATCHDOG must be 0 or 1"
#endif
#ifndef MK61_ENABLE_WATCHDOG_TEST
  #define MK61_ENABLE_WATCHDOG_TEST 0
#endif
#if MK61_ENABLE_WATCHDOG_TEST != 0 && MK61_ENABLE_WATCHDOG_TEST != 1
  #error "MK61_ENABLE_WATCHDOG_TEST must be 0 or 1"
#endif

// Shallow Cortex-M Sleep is entered only from a conservative top-level idle
// policy. SysTick remains the periodic keyboard wake source; STOP/STANDBY are
// deliberately not used.
#ifndef MK61_ENABLE_IDLE_WFI
  #define MK61_ENABLE_IDLE_WFI 1
#endif
#if MK61_ENABLE_IDLE_WFI != 0 && MK61_ENABLE_IDLE_WFI != 1
  #error "MK61_ENABLE_IDLE_WFI must be 0 or 1"
#endif

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
// отбирает сигнал у LCD, а электрическая нагрузка дисплея мешает генератору.
// Штатный источник здесь LSI. В CDU оба вывода LSE также заняты. На остальных
// поддерживаемых платах можно попробовать запустить LSE и перейти на LSI, если
// запуск не удался.
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
#if MK61_ENABLE_FOCAL != 0 && MK61_ENABLE_FOCAL != 1
  #error "MK61_ENABLE_FOCAL must be 0 or 1"
#endif

// TinyBASIC включен по умолчанию. Поставьте 0, чтобы убрать его
// редактор, рантайм и меню из прошивки.
#ifndef MK61_ENABLE_TINYBASIC
  #define MK61_ENABLE_TINYBASIC 1
#endif
#if MK61_ENABLE_TINYBASIC != 0 && MK61_ENABLE_TINYBASIC != 1
  #error "MK61_ENABLE_TINYBASIC must be 0 or 1"
#endif

// USB-экран хранит собственный монохромный кадровый буфер 192x64 за обычным
// API дисплея. По умолчанию он выключен, поскольку статические буферы расходуют
// ОЗУ. Этот ключ также разрешает сборку графических файловых модулей для
// LCD1602; их запуск всё равно требует активной сессии виртуального экрана.
#ifndef MK61_ENABLE_USB_SCREEN
  #define MK61_ENABLE_USB_SCREEN 0
#endif
#if MK61_ENABLE_USB_SCREEN != 0 && MK61_ENABLE_USB_SCREEN != 1
  #error "MK61_ENABLE_USB_SCREEN must be 0 or 1"
#endif

// На момент объявления файловых модулей полные профили ещё не раскрыты в
// MK61_DISPLAY_UC1609, поэтому учитываем и сами флаги готовых плат.
#if defined(MK61_DISPLAY_UC1609) || defined(DISPLAY_UC1609) || \
    defined(MK61_BOARD_CLASSIC_V2) || defined(MK61_BOARD_CLASSIC_V3) || \
    defined(MK61_BOARD_40TH) || MK61_ENABLE_USB_SCREEN
  #define MK61_HAS_COMPILED_GRAPHICS 1
#else
  #define MK61_HAS_COMPILED_GRAPHICS 0
#endif

// T2/.md доступен на любом экране: LCD1602 получает семантический plain text,
// UC1609 и USB-экран — форматированный монохромный документ с WBMP-блоками.
#ifndef MK61_ENABLE_MARKDOWN_VIEWER
  #define MK61_ENABLE_MARKDOWN_VIEWER 1
#endif
#if MK61_ENABLE_MARKDOWN_VIEWER != 0 && MK61_ENABLE_MARKDOWN_VIEWER != 1
  #error "MK61_ENABLE_MARKDOWN_VIEWER must be 0 or 1"
#endif

// Отдельный WBMP-viewer по умолчанию существует только без Markdown и при
// наличии физического или виртуального графического экрана. Явная прежняя
// комбинация WBMP=1, MARKDOWN=1 безопасна: Markdown всё равно имеет приоритет.
#ifndef MK61_ENABLE_WBMP_VIEWER
  #define MK61_ENABLE_WBMP_VIEWER \
    (MK61_HAS_COMPILED_GRAPHICS && !MK61_ENABLE_MARKDOWN_VIEWER)
#endif
#if MK61_ENABLE_WBMP_VIEWER != 0 && MK61_ENABLE_WBMP_VIEWER != 1
  #error "MK61_ENABLE_WBMP_VIEWER must be 0 or 1"
#endif

#define MK61_MARKDOWN_USES_WBMP \
  (MK61_ENABLE_MARKDOWN_VIEWER && MK61_HAS_COMPILED_GRAPHICS)
#define MK61_STANDALONE_WBMP_VIEWER_ENABLED \
  (MK61_ENABLE_WBMP_VIEWER && !MK61_ENABLE_MARKDOWN_VIEWER)
#if MK61_STANDALONE_WBMP_VIEWER_ENABLED && !MK61_HAS_COMPILED_GRAPHICS
  #error "MK61_ENABLE_WBMP_VIEWER requires UC1609 or MK61_ENABLE_USB_SCREEN=1"
#endif

// Консоль CHIP-8 выключена по умолчанию. C1 — двухбайтовый magic типа C5;
// .ch8 хранит стандартный сырой ROM без дополнительного заголовка.
#ifndef MK61_ENABLE_CHIP8
  #define MK61_ENABLE_CHIP8 0
#endif
#if MK61_ENABLE_CHIP8 != 0 && MK61_ENABLE_CHIP8 != 1
  #error "MK61_ENABLE_CHIP8 must be 0 or 1"
#endif
#if MK61_ENABLE_CHIP8 && !MK61_HAS_COMPILED_GRAPHICS
  #error "MK61_ENABLE_CHIP8 requires UC1609 or MK61_ENABLE_USB_SCREEN=1"
#endif

// F401CC вмещает основную прошивку, но почти не оставляет запаса во внутренней
// Flash для всех необязательных рантаймов. Поэтому его штатный профиль хранит
// включённые FOCAL, TinyBASIC и просмотрщики как загружаемые APP в C5.
// Остальные контроллеры сохраняют прежнюю встроенную компоновку. Явный ключ
// -DMK61_ENABLE_LOADABLE_MODULES=0/1 всегда имеет приоритет над профилем платы.
#ifndef MK61_ENABLE_LOADABLE_MODULES
  #if defined(ARDUINO_BLACKPILL_F401CC)
    #define MK61_ENABLE_LOADABLE_MODULES 1
  #else
    #define MK61_ENABLE_LOADABLE_MODULES 0
  #endif
#endif
#if MK61_ENABLE_LOADABLE_MODULES != 0 && MK61_ENABLE_LOADABLE_MODULES != 1
  #error "MK61_ENABLE_LOADABLE_MODULES must be 0 or 1"
#endif

// Ключ каждого системного компонента остаётся главным: выключенный компонент
// не получает ни встроенной реализации, ни APP-артефакта.
// Сам MK61_ENABLE_LOADABLE_MODULES включает общий загрузчик пользовательских
// APP и единый SRAM-overlay даже тогда, когда все системные APP выключены.
#define MK61_FOCAL_IS_LOADABLE \
  (MK61_ENABLE_LOADABLE_MODULES && MK61_ENABLE_FOCAL)
#define MK61_TINYBASIC_IS_LOADABLE \
  (MK61_ENABLE_LOADABLE_MODULES && MK61_ENABLE_TINYBASIC)
#define MK61_WBMP_VIEWER_IS_LOADABLE \
  (MK61_ENABLE_LOADABLE_MODULES && \
   MK61_STANDALONE_WBMP_VIEWER_ENABLED)
#define MK61_MARKDOWN_VIEWER_IS_LOADABLE \
  (MK61_ENABLE_LOADABLE_MODULES && MK61_ENABLE_MARKDOWN_VIEWER)
#define MK61_CHIP8_IS_LOADABLE \
  (MK61_ENABLE_LOADABLE_MODULES && MK61_ENABLE_CHIP8)
#define MK61_ANY_LOADABLE_MODULE (MK61_ENABLE_LOADABLE_MODULES)

#define MK61_FOCAL_IS_BUILTIN \
  (MK61_ENABLE_FOCAL && !MK61_ENABLE_LOADABLE_MODULES)
#define MK61_TINYBASIC_IS_BUILTIN \
  (MK61_ENABLE_TINYBASIC && !MK61_ENABLE_LOADABLE_MODULES)
#define MK61_WBMP_VIEWER_IS_BUILTIN \
  (MK61_STANDALONE_WBMP_VIEWER_ENABLED && \
   !MK61_ENABLE_LOADABLE_MODULES)
#define MK61_MARKDOWN_VIEWER_IS_BUILTIN \
  (MK61_ENABLE_MARKDOWN_VIEWER && !MK61_ENABLE_LOADABLE_MODULES)
#define MK61_CHIP8_IS_BUILTIN \
  (MK61_ENABLE_CHIP8 && !MK61_ENABLE_LOADABLE_MODULES)

// Графический Markdown владеет полным I1-viewer и WBMP-декодером: он показывает
// как локальные блоки изображений, так и самостоятельные .wbmp. Загружаемые
// APP делят один overlay и не могут вызывать друг друга, поэтому WBMP.APP
// существует только в конфигурации без Markdown.
#define MK61_IMAGE1_VIEWER_IS_BUILTIN \
  (MK61_WBMP_VIEWER_IS_BUILTIN || \
   (MK61_MARKDOWN_VIEWER_IS_BUILTIN && MK61_MARKDOWN_USES_WBMP))
#define MK61_WBMP_DECODER_IS_BUILTIN \
  (MK61_IMAGE1_VIEWER_IS_BUILTIN)

#define MK61_ANY_FULLSCREEN_FILE \
  (MK61_STANDALONE_WBMP_VIEWER_ENABLED || MK61_ENABLE_CHIP8 || \
   (MK61_ENABLE_MARKDOWN_VIEWER && MK61_HAS_COMPILED_GRAPHICS))

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

// Mini/LCD1602 has only the NOR client on SPI1, so its measured arbiter and DMA
// backend are enabled by default. Physical UC1609 profiles stay on their
// original polling path until the display is moved behind the same ownership
// boundary and accepted on real Classic/40th hardware.
#ifndef MK61_ENABLE_SPI1_ARBITER
  #if defined(MK61_DISPLAY_UC1609)
    #define MK61_ENABLE_SPI1_ARBITER 0
  #else
    #define MK61_ENABLE_SPI1_ARBITER 1
  #endif
#endif
#if MK61_ENABLE_SPI1_ARBITER != 0 && MK61_ENABLE_SPI1_ARBITER != 1
  #error "MK61_ENABLE_SPI1_ARBITER must be 0 or 1"
#endif

// Long SPI1 buffers can use DMA2 S2/S3 after the polling arbiter has granted
// exclusive ownership. The measured threshold is deliberately configurable;
// short command/address transfers remain on the cheaper polling path.
#ifndef MK61_ENABLE_SPI1_DMA
  #define MK61_ENABLE_SPI1_DMA MK61_ENABLE_SPI1_ARBITER
#endif
#if MK61_ENABLE_SPI1_DMA != 0 && MK61_ENABLE_SPI1_DMA != 1
  #error "MK61_ENABLE_SPI1_DMA must be 0 or 1"
#endif
#if MK61_ENABLE_SPI1_DMA && !MK61_ENABLE_SPI1_ARBITER
  #error "MK61_ENABLE_SPI1_DMA requires MK61_ENABLE_SPI1_ARBITER=1"
#endif
#ifndef MK61_SPI1_DMA_THRESHOLD
  #define MK61_SPI1_DMA_THRESHOLD 128
#endif
#if MK61_SPI1_DMA_THRESHOLD < 1 || MK61_SPI1_DMA_THRESHOLD > 65535
  #error "MK61_SPI1_DMA_THRESHOLD must be in 1..65535"
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

// На F411 небольшие таблицы микрокоманд выгодно держать в однократной SRAM:
// случайные обращения к ним находятся в самом горячем цикле эмулятора.
// 0 = Flash, 1 = микрокоманды и DCW (~1.1 КиБ SRAM), 2 = также AND_AMK
// (~7.1 КиБ SRAM суммарно). F401 с 64 КиБ оставляет SRAM для System APP.
#ifndef MK61_CORE_HOT_TABLES_IN_SRAM
  #if defined(STM32F411xE)
    #define MK61_CORE_HOT_TABLES_IN_SRAM 2
  #else
    #define MK61_CORE_HOT_TABLES_IN_SRAM 0
  #endif
#endif
#if MK61_CORE_HOT_TABLES_IN_SRAM < 0 || MK61_CORE_HOT_TABLES_IN_SRAM > 2
  #error "MK61_CORE_HOT_TABLES_IN_SRAM must be 0, 1, or 2"
#endif

// Три последовательных Tick объединяются в один внешний вызов на микротакт.
// Тела остаются раздельными в исходнике, но встраиваются в общий wrapper:
// порядок эмуляции не меняется, а F411 тратит меньше времени на ABI-обвязку.
#ifndef MK61_CORE_MERGED_TICK
  #define MK61_CORE_MERGED_TICK 1
#endif
#if MK61_CORE_MERGED_TICK != 0 && MK61_CORE_MERGED_TICK != 1
  #error "MK61_CORE_MERGED_TICK must be 0 or 1"
#endif
#if MK61_CORE_MERGED_TICK && MK61_DWT_CORE_DETAIL
  #error "MK61_CORE_MERGED_TICK is incompatible with per-chip DWT detail"
#endif

// Полное разворачивание расписания уменьшает цену внутреннего цикла.
// На F411 оно оказалось на 5.1% быстрее компактных циклов (+112 байт Flash).
#ifndef MK61_CORE_UNROLL_SCHEDULE
  #define MK61_CORE_UNROLL_SCHEDULE 1
#endif
#if MK61_CORE_UNROLL_SCHEDULE != 0 && MK61_CORE_UNROLL_SCHEDULE != 1
  #error "MK61_CORE_UNROLL_SCHEDULE must be 0 or 1"
#endif

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
    constexpr class_calc_config(void) : disassm(false), output_IP(false) {}
};

namespace cfg {

// Измеренная совместимая скорость прежнего loop-счётчика: 13 шагов за 15 с.
// Таймер задаётся в микросекундах; округление даёт ошибку меньше 1 ppm от
// целевого периода 15/13 с ещё до аппаратного квантования PSC/ARR.
static constexpr u32    CLASSIC_MK61_PERIOD_NUMERATOR = 15;
static constexpr u32    CLASSIC_MK61_PERIOD_DENOMINATOR = 13;
static constexpr u32    CLASSIC_MK61_PERIOD_US =  1153846;
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
