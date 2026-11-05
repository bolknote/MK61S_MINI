# Инструменты MK61S

В корне находятся две пользовательские команды:

| Команда | Назначение |
| --- | --- |
| `mkc.cmd` | Файловый менеджер: копирование, просмотр и работа с файлами устройства |
| `mk61-firmware.cmd` | Выбор профиля, сборка прошивки, DFU-загрузка STM32 и установка программ |

Лаунчеры работают на Windows и macOS/Linux. Без `--target` сборщик открывает
привычное меню STM32. Для PicoCalc выберите `--target picocalc-pico-h`.

```sh
./tools/mkc.cmd --help
./tools/mk61-firmware.cmd --list-targets
./tools/mk61-firmware.cmd --mcu f411 --profile classic-v3 --build
./tools/mk61-firmware.cmd --target picocalc-pico-h --build --fetch-sdk
./tools/mk61-firmware.cmd --target picocalc-pico-h --package
```

PicoCalc `--build` собирает прошивку и APP; `--package` проверяет уже готовый
комплект и создаёт архив. Действия можно объединить. Упаковка сохраняет
существующие требования к проверкам и аппаратным свидетельствам.
`--target picocalc-pico-h --help` показывает пути SDK, компилятора и выходных
каталогов. Для PicoCalc нужен Python 3; сборка STM32 на Windows сохраняет
PowerShell/.NET-путь без обязательного Python.

После «Собрать и прошить» STM32-сборщик ждёт последовательный порт и устанавливает
System текущей сборки. Повторная установка доступна через `--install-apps`.
На macOS/Linux MKC использует `arduino-cli`, Perl и `iconv`; на Windows —
PowerShell. Другие программы должны освободить порт.

## Каталоги и внутренние команды

Внутренние инструменты можно запускать непосредственно для разработки и CI.
Их имена описывают действия; язык реализации не определяет каталог.

| Каталог | Инструменты и назначение |
| --- | --- |
| `mkc/` | `mkc.sh`, `mkc.ps1` — клиенты; `m8_codec.pl` — M8-кодек Bash-клиента |
| `firmware/cli/` | Bash- и PowerShell-меню пользовательского сборщика |
| `firmware/stm32/` | `build-gcc.cmd`, `build.ps1` — прямая GCC-сборка; `build-standalone.py` — CLI/CI-сборка; `build_f401_bundle.sh` — native-комплект с System и пользовательскими APP-манифестами; `install_gcc_dependencies.py`, `.ps1` — установка закреплённого GCC; CMake, SDK, compile policy и проверки Flash/RAM |
| `firmware/picocalc/` | `firmware.py` — общий вход; `build_picocalc.py` — прошивка; `package_picocalc.py` — проверка и упаковка комплекта |
| `firmware/dfu/` | `dfu.sh`, `dfu.ps1`, `upload.ps1` — загрузка STM32 через DFU |
| `apps/portable/` | `build_portable_app.py` — самостоятельные C/C++/Rust APP для STM32/PicoCalc; `build-portable-app.ps1` — Windows-сборка системных APP |
| `apps/system/` | `build_system_app_bundle.py`, `build-system-app-bundle.ps1` — каталог System для STM32; `build_picocalc_apps.py` — комплект PicoCalc APP; `build_terminal_help.py`, `build-terminal-help.ps1` — справка из ELF |
| `apps/packer/` | Упаковщики APP на C++/Python/.NET, `build.ps1` для нативного упаковщика, релокации, linker script и исходники ZX0 |
| `programs/` | `program_pack.py` — CRC32 + ZX0 для команды `load`; `build_mk61_program_pack.sh`, `mk61_program_pack.cpp` — нативный упаковщик; `program_bundle.py` — подбор, экспорт и установка совместимых программ |
| `fonts/` | `build_fmk_font.sh`, `fmk_font.cpp` — FreeType → FMK; `build_fmk_from_ui_atlas.py` — атлас → FMK; `font_preview.cpp`, `font_preview_study.py`, HTML — экспорт и сравнение шрифтов; атласы, исходные данные и упаковщики лицензий |
| `arduino/` | `mk61-arduino-board.cmd` и установщики плат; `install_arduino_dependencies.ps1` — зависимости STM32duino; payload и IDE-хуки |
| `arduino/compat/` | `portable-layout.py` — SRAM/linker-разметка; `protect-core-lto.py`, `protect-usb-lto.py` — LTO-барьеры для проверок совместимого STM32duino-пути |
| `device/` | `sync_picocalc_clock.py` — чтение/синхронизация RTC; `vfat_diagnostic.py` — расшифровка USB-диска |
| `apps/spectrum/` | `build_spectrum_app.py` — эмулятор; `build_spectrum_library.py` — игры; `fetch_spectrum_devices.py` — закреплённые ROM; `spectrum_media.py` — образы носителей; `spectrum_rom_cache.py` — ROM-кэш RP2040 |
| `apps/urq/` | `build_urq_app.py` — проигрыватель; `qst2urq.py` — конвертер; `build_urq_library.py` — библиотека; адаптации, исходники и лицензии; `oracle.js` — эталонный интерпретатор для сравнительных тестов |

Исследования, профилирование и генераторы штатных ресурсов находятся в
[`dev/tools`](../dev/tools/README.md), общие модули — в
[`dev/lib`](../dev/lib/README.md). Бинарники, кеши компиляторов и комплекты
сохраняются в `.build`, отдельно от исходников.

Параллельные реализации упаковщиков используются разными путями сборки:
C++ даёт нативный оптимальный ZX0, Python служит переносимым вариантом,
C# обслуживает Windows без host C++ и Python.

## Собственные приложения и шрифты

[Быстрый старт C/Rust](../doc/src/MK61s-mini-APP-Quickstart.md) ·
[Руководство C/C++](../doc/src/MK61s-mini-APP-Programming.md) ·
[SDK](../sdk/portable/README.md) · [FMK](../doc/src/MK61s-mini-FMK.md).

Калькуляторные `.bin` размером 5…4096 байт MKC копирует побайтно;
F3 показывает hex, F4 оставляет их доступными только для чтения.

## Установка комплекта программ

`mk61-firmware.cmd` умеет показать состав, установить программы отдельно или
вместе с System по фактическим возможностям готовой сборки:

```sh
./tools/mk61-firmware.cmd --mcu f401 --profile classic-v2 --preview-programs
./tools/mk61-firmware.cmd --mcu f401 --profile classic-v2 --install-all
```

Подбор включает требования интерпретаторов, экрана, CPU/ABI и ограничения
файлов. Листы идут вместе с SHEET.APP. Изменённые листы и пользовательские
сохранения не заменяются. Протокол проверяет размер и CRC при загрузке;
дополнительное скачивание включается `--verify-programs`. Подбор требует
Python 3.10+. Старая сборка без `program-capabilities.json` требует пересборки.

`program_bundle.py` предоставляет тот же просмотр, установку и экспорт для
готовых STM32/PicoCalc-комплектов; по умолчанию ничего на устройство не пишет:

```sh
python3 tools/programs/program_bundle.py --bundle .build/firmware/picocalc-pico-h
```

[Подробности обновления и команды](../doc/design/Program-bundle-installation.md).

## Диагностика USB-диска

При ошибке USB-диска экран показывает `USB E12xx`. После выхода из режима
диска команда `vlog` возвращает последнюю причину, например:

```text
VFAT v=1 code=1221 phase=3 flags=0 actual=7492 limit=1536 subject=524541444D45
```

Это `File too large`: файл `README` (поле `subject` — безопасный UTF-8 prefix,
закодированный hex) имеет 7492 байта при лимите 1536. Расшифровать запись или
целый сохранённый transcript можно командой
`python3 tools/device/vfat_diagnostic.py < terminal.log`. `phase`: 1 — session,
2 — cache, 3 — directory entry, 4 — chain, 5 — validate, 6 — prepare,
7 — apply, 8 — commit. В `flags` бит 0 означает возможность повторной попытки,
бит 1 — усечение имени. `vlog clear` очищает запись; успешный реальный импорт
тоже очищает её. Обычный выход из USB-диска без записи причину не стирает.
Wire version и номера причин заданы в `code/virtual_fat_diagnostic.hpp`;
неизвестные версии нельзя молча разбирать как версию 1.
