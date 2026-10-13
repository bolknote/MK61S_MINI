# Узкие аппаратные драйверы STM32F401/F411

Продолжение замены ADC, SPI1/DMA, LCD1602 и RTC. Arduino Core 2.12.0,
CMSIS и закреплённые LL-функции ST остаются источником регистров,
startup, системных часов и SysTick. Полного перехода на самостоятельный
bare metal runtime эта работа не делает.

## PWM и EXTI

`stm32f4_buzzer.hpp` задаёт только квалифицированные маршруты:
PA0 → TIM2 CH1 AF1, PB9 → TIM4 CH4 AF2, PB10 → TIM2 CH3 AF1.
`PIN_BUZZER` проверяется при компиляции; общего поиска по PinMap_TIM нет.
GPIO настраивается масками, соседние пины сохраняются. Переход на AF
происходит после настройки таймера; при остановке выход удерживается низким.

`stm32f4_keyboard_exti.hpp` владеет только PB4..PB8 и IRQ EXTI4/EXTI9_5.
Остальные линии EXTI сохраняются. Событие фиксируется по pending-флагу,
даже если клавиша уже отпущена к чтению GPIO. W1C очищает только замеченные
флаги. Arduino EXTI callback table исключается через поддерживаемый core
макрос HAL_EXTI_MODULE_DISABLED. STOP доступен только на исходно
поддерживаемых профилях. Аппаратная проверка глубокого сна отложена
пользователем; модель и release ELF gate не заменяют её.

UC1609 на этих MCU имеет только аппаратный SPI-конструктор; software SPI
и CustomshiftOut исключены. Иные MCU сохраняют прежние реализации.

## OTG FS

`stm32f4_usb_device.cpp` заменяет HAL PCD bridge, сохраняя CDC/MSC и
проектные защитные обёртки. Поддерживается только embedded FS PHY,
device mode, четыре endpoint'а, без host/HS/ISO/USB DMA. Используются
закреплённые LL-функции STM32F4 для настройки контроллера.

RX FIFO — 64 слова; TX0/1/2 — по 64, TX3 — 8 слов, всего 264 из 320.
CDC использует OUT1, IN2 и notification IN3; MSC — OUT1/IN1.
Короткие невыравненные IN-пакеты не читают байты за границей буфера.
OUT копирует лишь объявленную ёмкость, но сообщает полную принятую длину,
чтобы MSC мог отклонить некорректный CBW. FIFO дренируется до callbacks.
Изменения endpoint'ов защищены сохранением/восстановлением PRIMASK.

`stm32f4_usbd_def.h` и `stm32f4_usbd_ctlreq.c` — копии файлов закреплённого
STM32duino middleware с сохранёнными copyright/license; условия компонента
в `code/STM32_USB_DEVICE_LICENSE.md`. Изменения:
endpoint arrays 16 → 4 и проверка зарезервированных битов/номера endpoint
до индексации в USBD_StdEPReq. Общий handle уменьшается 732 → 252 байта.
Проверка ELF требует размер 252, если USB handle присутствует.

Arduino `build_opt.h` принудительно включает общий ABI header во все
C/C++ единицы, пропуская assembler. Prelink Python/PowerShell компилирует
bridge и bounded control requests из snapshot `build/sketch`, заменяя
соответствующие объекты USBDevice; исходники установленного core не меняются.
CMake убирает те же два штатных файла и добавляет проектные с отдельными
build defines. Обычные sketch/resident объекты этих файлов пусты.
Два wrap-target файла middleware сохраняют барьер `-fno-lto`.

ARM-тест `tests/stm32f4_usb_arm_self_test.py ELF` исполняет именно итоговый
драйвер с моделью MMIO и callbacks: init, границы, W1C, IN rearm, RX queue,
SETUP, reset/enumeration, suspend/resume, stop/deinit/reinit. Нужен Unicorn.

## Форматирование

`compact_format` сохраняет C ABI snprintf/vsnprintf и System APP format
service для integer/string/char. Поддерживает флаги, ширину/точность,
звёздочки, один h/l/L и %n. На ARM long/int/pointer — 32 бита.
Как прежний integer-only nano printf, e/E/f/F/g/G consumes double без
вывода; 64-bit integer, z/j/t и hex float не входят в существующий ABI.
Обработка ограниченного буфера сохраняет полную длину и NUL-терминатор;
огромное padding не выполняет миллиарды холостых итераций после truncation.

Сохраняется историческое nano `%#o` для нуля без precision: `00`.
Для octal с явной precision используется определённое стандартное поведение:
старый nano сравнивает precision с прежним неинициализированным digit count,
поэтому результат зависит от содержимого стека. Такие случаи проверяются
против host printf, остальные — дифференциально на production ARM ELF.

## SPI polling

Источником измеренного замедления предыдущей замены оказался polling:
каждый байт проходил через отдельные ожидания и generic buffer trampoline.
Теперь scalar transfer прямой, обычные ready-флаги обходятся без чтения
SysTick, wire wait сначала делает короткую ограниченную серию probes,
затем проверяет 100 ms deadline каждые 32 неуспешных опроса. Для buffer
сохраняется общий deadline; для scalar/transaction — ограничение ожидания
конкретного флага. При таймауте сохраняется reset/recovery SPI.
CR1/CR2 переписываются только при реальном изменении настройки.

Аппаратный A/B SPI измеряется на одинаковом source snapshot, flags и
System APP. Изменение памяти VM, алгоритма игры или количества узлов
не относится к результатам аппаратного драйвера.

## WS0010 без физической графики

При MK61_WS0010_GRAPHICS_100X16=0 graphics owner теперь constexpr NONE;
физический graphicsMode всегда false. Виртуальный USB Screen сохраняет
собственную проверку активности. Неиспользуемое графическое состояние часов
и проверки owner исключаются, включая сборку без LTO.

Отдельный сравнительный F401 budget WS0010/A00 установлен в 8 байт.
Именованные профильные данные отличаются всего на 2 байта в обоих сравнениях:
дополнительный пункт меню/настройка OLED, за вычетом меньшего объекта дисплея.
Прежний нулевой предел проходил за счёт padding крупных общих драйверов.
После их удаления linker alignment даёт delta 8. Абсолютные RAM/Flash budgets
и предел добавления graphics state 16 байт сохраняются; framebuffer не добавлен.

DMA sleep проверяет completed/errors повторно с установленным PRIMASK перед
WFI. Иначе IRQ между обычной проверкой и WFI уже обработан, и CPU спит
до следующего IRQ, добавляя до миллисекунды к готовой передаче.
На Cortex-M4 pending enabled IRQ пробуждает WFI и с установленным PRIMASK;
обработчик выполняется после восстановления маски.
Источник: [Arm CMSIS WFI](https://arm-software.github.io/CMSIS_5/5.8.0/Core/html/group__intrinsic__CPU__gr.html).
Regression model вводит completion именно в это окно и требует ноль WFI;
отдельно моделирует pending IRQ под маской, сохранение SCR/PRIMASK и timeout.
