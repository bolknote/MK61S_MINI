![GitHub](https://img.shields.io/badge/github-%23121011.svg?style=for-the-badge&logo=github&logoColor=white)
![C](https://img.shields.io/badge/c-%2300599C.svg?style=for-the-badge&logo=c&logoColor=white)
![C++](https://img.shields.io/badge/c++-%2300599C.svg?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![Arduino](https://img.shields.io/badge/-Arduino-00979D?style=for-the-badge&logo=Arduino&logoColor=white)

# MK61S — mini, Classic и PicoCalc

Прошивка, программы и инструменты для ретроконсоли «МК-61s». Проект объединяет
собственные платы **mini**, **Classic** и **40th** на STM32 и порт для
**ClockworkPi PicoCalc с Raspberry Pi Pico H**. У них общее ядро эмуляции
«Электроники МК-61», языки и форматы программ, но разные драйверы, экраны,
клавиатуры и способы хранения файлов.

Имя репозитория `MK61S_MINI` сохранилось от первоначального варианта mini.
Сейчас разработка охватывает все перечисленные модели.

Обсуждение проекта: [группа в Telegram](https://t.me/mk61s).

## Поддерживаемые устройства

| Модель | Контроллер | Экран | Профили сборки |
| --- | --- | --- | --- |
| mini V2 | BlackPill STM32F411CE / STM32F401CC | LCD1602 A00 или A02, 16×2 символа | `mini-v2-a00`, `mini-v2-a02` |
| mini V3 | BlackPill STM32F411CE / STM32F401CC | LCD1602 A00/A02 или OLED1602 WEH001602A/WS0010 | `mini-v3-a00`, `mini-v3-a02`, `mini-v3-ws0010` |
| Classic V2 / V3 | STM32F411CE / STM32F401CC | Графический UC1609, 192×64 | `classic-v2`, `classic-v3` |
| 40th | STM32F411CE / STM32F401CC | Графический UC1609, 192×64 | `40th` |
| PicoCalc v2.0 + Pico H | RP2040, два ядра Cortex-M0+ | ST7365P, 320×320 | `picocalc-pico-h` |

Для STM32 контроллер выбирается отдельно от платы и дисплея. Прошивки F401,
F411 и Pico H собираются для своих процессоров и не взаимозаменяемы.
Основной STM32-вариант — F411. Для F401 есть отдельные сборки с System APP
и меньшими лимитами Flash/RAM; квалификация части конфигураций продолжается.
Таблица перечисляет реализованные профили; результаты их проверок относятся
к конкретному коммиту и запуску CI.
Точные сочетания, распиновка и особенности ревизий STM32 описаны в
[аппаратном руководстве](doc/src/MK61s-mini-Hardware.md), PicoCalc — в
[руководстве порта](ports/picocalc/README.md).

**Classic** использует собственную клавиатурную раскладку и графический
интерфейс 192×64: индикатор и стек, регистры, меню, Проводник, редакторы,
документы, изображения и графические приложения. Для V2, V3 и 40th есть
отдельные профили: их различия учитываются при сборке.

**PicoCalc** использует QWERTY-клавиатуру корпуса, microSD и штатные 8 МиБ
PSRAM. Калькулятор, меню, Проводник, редакторы и адаптированные приложения
рисуются в родных 320×320 пикселях. PSRAM используется для буферов, кешей
и истории отмен приложений; экран и периферия обслуживаются вторым ядром.
У порта отдельная сборка на Pico SDK. Время встроенного RTC Pico H теряется
после полного снятия питания; остальные особенности и отчёты аппаратных
проверок собраны в [документации PicoCalc](ports/picocalc/README.md).

## Что умеет прошивка

- Эмуляция МК-61: обратная польская запись, стек, регистры, ввод и пошаговое
  выполнение программ; обычная и расширенная память, дополнительные команды.
- Русский и английский интерфейсы, настройки, часы, будильники и сон.
- Файлы и Проводник: каталоги, поиск, запуск, создание, переименование,
  удаление, текстовый редактор и значки папок на графических экранах.
- Терминал и сценарии `.m61`: загрузка программ, условия, вложенные файлы,
  обработчики `trap`, привязки клавиш и таймеров, запуск по `autoexec.m61`.
- TinyBASIC и FOCAL, доступ к калькуляторным регистрам и графике;
  просмотр Markdown и WBMP, загружаемые шрифты FMK.
- CHIP-8, USB Screen и самостоятельные приложения `.APP` на C, C++ и Rust.
  В комплект программ входят игры, ELIZA и электронная таблица SHEET.

Состав зависит от профиля, экрана и ключей сборки. На F401 крупные системные
компоненты загружаются из `/System` как APP; на F411 размещение выбирается
при сборке, а на PicoCalc системные службы встроены в UF2. Пользовательские
APP собираются отдельно для STM32 или RP2040. Исходники, примеры и описание
контракта находятся в [SDK](sdk/portable/README.md).

## Готовые прошивки и программы

- **STM32:** [GitHub Releases](https://github.com/bolknote/MK61S_MINI/releases) —
  опубликованные комплекты для конкретных плат, дисплеев и MCU. Профили и
  ресурсные бюджеты релизных сборок задаёт [релизный контракт](tools/release-contract.json);
  наличие варианта в контракте само по себе не означает успешный выпуск.
- **PicoCalc / Pico H:** артефакт `mk61s-picocalc-pico-h` успешного запуска
  ветки `main` в [PicoCalc Pico H](https://github.com/bolknote/MK61S_MINI/actions/workflows/picocalc.yml).
  Внутри находятся UF2, пользовательские APP, шрифты, игры и примеры для microSD.
- [Каталог `programs`](programs/README.markdown) содержит исходники и готовые
  файлы игр, библиотеку программ МК-61, примеры BASIC/FOCAL, CHIP-8 ROM,
  шрифты и листы `.mks`. Для PicoCalc берите нативные APP из его комплекта.

Результаты локальных сборок сохраняются в игнорируемом `.build/firmware/`.
На STM32 используйте resident-прошивку и каталог `System` из одного комплекта.

## Сборка STM32: mini, Classic и 40th

Штатная сборка использует независимый SDK проекта, GNU Arm GCC, CMake и Ninja.
Установленные STM32duino, Arduino IDE и `arduino-cli` для неё не нужны.
Закреплённый GNU Arm GCC можно установить в `.build/toolchains`:

```powershell
pwsh -NoProfile -File tools/install_gcc_dependencies.ps1
```

В Windows вместо `pwsh` доступен встроенный `powershell.exe`.
Для сборки нужны CMake 3.21+ и Ninja; на macOS/Linux также `pwsh` и
host-компилятор C++17 для упаковщика APP. Подробности зависимостей и SDK —
[здесь](doc/design/STM32-independent-sdk.md).

Интерактивный выбор контроллера, платы, экрана и компонентов:

```sh
./tools/mk61-firmware.cmd
```

В Windows тот же файл запускается как `tools\mk61-firmware.cmd`.
Лаунчер выбирает Bash или PowerShell для текущей системы.

Примеры сборки без загрузки в устройство:

```sh
./tools/mk61-firmware.cmd --list-profiles
./tools/mk61-firmware.cmd --mcu f411 --profile classic-v3 --build
./tools/mk61-firmware.cmd --mcu f411 --profile mini-v3-a00 --build
./tools/mk61-firmware.cmd --mcu f401 --profile classic-v2 --build
```

Прямая GCC-сборка тех же профилей:

```powershell
./tools/build-gcc.cmd -Mcu f411 -Profile classic-v3
./tools/build-gcc.cmd -Mcu f401 -Profile mini-v3-a00
```

`mk61-firmware` также поддерживает DFU-загрузку и установку System APP через
COM/CDC с обратным чтением и проверкой файлов. Повторная установка без
перепрошивки доступна через `--install-apps`.
[Команды и порядок работы](tools/README.md),
[формат и установка APP](doc/src/MK61s-mini-APP.md).

Для работы в **Arduino IDE** установите проектные платы командой
`./tools/mk61-arduino-board.cmd`, откройте `code/code.ino` и выберите
`MK61s F401 + APP` или `MK61s F411 + APP`, затем нужные платформу и экран.
Пакет использует тот же собственный SDK и компилятор.
[Подробная инструкция](doc/src/MK61s-mini-Arduino-IDE.md).

## Сборка PicoCalc с Pico H

Нужны Python 3, CMake, Ninja и GNU Arm GCC; для упаковки пользовательских APP —
host-компилятор C++17. Комплект также включает пример на Rust, для которого
нужен Rust с установленной целевой платформой `thumbv6m-none-eabi`.

```sh
python3 tools/build_picocalc.py --profile picocalc-pico-h --fetch-sdk
python3 tools/build_picocalc_apps.py
python3 tools/package_picocalc.py
```

Первая команда собирает прошивку и при необходимости скачивает закреплённые
Pico SDK и TinyUSB. Вторая собирает пользовательские APP для Cortex-M0+,
третья упаковывает прошивку и содержимое microSD. Результат находится в
`.build/firmware/picocalc-pico-h/`: UF2, ELF, manifest с размерами и SHA-256,
каталог приложений и ZIP-комплект.

Уже установленные SDK и компилятор можно передать явно:

```sh
python3 tools/build_picocalc.py --sdk /path/to/pico-sdk --toolchain /path/to/gcc/bin
python3 tools/build_picocalc_apps.py --toolchain /path/to/gcc/bin
```

Для первой прошивки используется **Micro-USB самого Pico H**: удерживая
BOOTSEL при подключении, откройте диск `RPI-RP2` и скопируйте на него UF2.
Для экрана и клавиатуры должна быть включена основная плата PicoCalc.
USB-C корпуса предоставляет питание и последовательный интерфейс через UART.
[Подключение, управление и аппаратные ограничения](ports/picocalc/README.md).

## Файлы и переносимость

На **STM32** файлы хранятся в C9 во внешней SPI flash. Режим USB-диска
представляет их компьютеру как виртуальный FAT/VFAT-том. Комплект системных
APP помещается в `/System`, пользовательские программы — в обычные каталоги.
[Устройство хранилища](doc/src/MK61s-mini-Storage.md).

На **PicoCalc** используется настоящая FAT/FAT32/exFAT на microSD. USB-диск
даёт компьютеру доступ к карте целиком; прошивка на время этой сессии
размонтирует свою файловую систему. Системные службы уже находятся в UF2,
а пользовательские APP и данные остаются на карте.

Программы МК-61, сценарии M61 и файлы BASIC/FOCAL используются общим
исполнителем; графические ресурсы могут иметь варианты для разных экранов.
Нативные `.APP` для STM32 Cortex-M4 и Pico H Cortex-M0+ требуют разных
сборок. Калькуляторный `.bin` — программа МК-61, он отличается от
resident `.bin` с машинным кодом прошивки STM32.

## Документация

| Тема | Руководство |
| --- | --- |
| Все руководства, включая PDF | [Оглавление](doc/readme.md) |
| Платы, дисплеи и распиновка STM32 | [Аппаратные профили](doc/src/MK61s-mini-Hardware.md) |
| PicoCalc / Pico H | [Сборка, управление, экран 320×320, microSD, PSRAM и диагностика](ports/picocalc/README.md) |
| Инструменты сборки и файловый менеджер MKC | [Команды `tools`](tools/README.md) |
| Самостоятельный STM32 SDK и драйверы | [Сборка](doc/design/STM32-independent-sdk.md), [драйверы](doc/design/STM32-hardware-core.md) |
| Arduino IDE | [Установка и сборка](doc/src/MK61s-mini-Arduino-IDE.md) |
| Файлы, C9 и USB-диск | [Хранилище](doc/src/MK61s-mini-Storage.md) |
| Терминал и сценарии | [Терминал](doc/src/MK61s-mini-Terminal.md), [M61](doc/src/MK61s-mini-M61.md), [trap](doc/src/MK61s-mini-M61-Trap.md) |
| Языки | [TinyBASIC](doc/src/MK61s-mini-TinyBASIC.md), [FOCAL](doc/src/MK61s-mini-FOCAL.md) |
| Собственные приложения | [Быстрый старт C/Rust](doc/src/MK61s-mini-APP-Quickstart.md), [C/C++](doc/src/MK61s-mini-APP-Programming.md), [SDK ABI 6](sdk/portable/README.md) |
| Формат и установка APP | [APP](doc/src/MK61s-mini-APP.md) |
| Графика и шрифты | [Markdown](doc/src/MK61s-mini-Markdown.md), [WBMP](doc/src/MK61s-mini-WBMP.md), [FMK](doc/src/MK61s-mini-FMK.md) |
| Настольный USB-экран | [Протокол и клиент](doc/src/MK61s-mini-USB-Screen.md) |
| CHIP-8 | [Консоль и ROM](doc/src/MK61s-mini-CHIP8.md) |
| Часы RTC | [Настройка и синхронизация](doc/src/MK61s-mini-RTC.md) |
| Готовые программы и игры | [Каталог](programs/README.markdown), [игры](programs/games/README.markdown), [SHEET](examples/portable-apps/SHEET/README.md) |

## Проверки

Общий host-набор:

```sh
tests/run_all_tests.sh
```

Строгий host-вход CI с Clang 18 и ASan/UBSan:

```sh
tests/run_ci_strict.sh
```

STM32 release preflight и отдельный host-набор PicoCalc:

```sh
tests/run_release_preflight.sh
bash tests/run_picocalc_tests.sh
```

CI [Firmware release](.github/workflows/firmware-release.yml) проверяет STM32
по релизному контракту, собирает комплекты и публикует артефакты.
[PicoCalc Pico H](.github/workflows/picocalc.yml) проверяет порт, ARMv6-M APP,
ресурсы, упаковку и совместимость сборок STM32. Успешная сборка и host-тесты
не заменяют проверку конкретного устройства.

## История mini и участники

Проект вырос из [эмулятора МК-61s Vitasam](https://web.archive.org/web/20231130170055/https://gitlab.com/vitasam/mk61s/).
Ядро основано на работе [Феликса Лазарева](https://github.com/fixelsan/emu145)
и сохраняет особенности исходной «Электроники МК-61», включая её «ЕГГОГ».

Первоначальная цель mini — бюджетное устройство, которое можно повторить
с обычным паяльником и начальными навыками пайки. Плата ограничена размером
10×10 см и использует готовую BlackPill. Корпус mini V3 имеет размеры
99×99×19 мм; эти размеры относятся именно к mini.

![mini V3 в сборе](img/mk-61s-mini-c.jpg)

[Описание mini](doc/MK61s-mini-Documentation.pdf),
[сборка](doc/MK61s-mini-Assembly.pdf),
[прошивка](doc/MK61s-mini-Programming.pdf),
[OLED WS0010](doc/src/MK61s-mini-WS0010.md),
[статья о проекте](https://habr.com/ru/articles/860226/),
[видео сборки FANJET](https://www.youtube.com/watch?v=JBStgbfmuOs),
[плата в Open Source Hardware Lab](https://oshwlab.com/un7fgo/mk61s_v1_copy_copy_copy_copy).

Участники проекта:

- [Digitalinvitro](https://github.com/digitalinvitro) — программный код.
- [Vitasam](https://github.com/vitasam) — программный код.
- [UN7FGO](http://gengen.ru/) — схема, печатная плата и документация.
- [Bolknote](https://github.com/bolknote/) — программный код: файловая система
  и Проводник, терминал и M61, языки и редакторы, APP, шрифты и графический
  интерфейс, порт PicoCalc.
