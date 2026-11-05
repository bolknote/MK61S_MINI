# Пользовательские инструменты MK61S

В `tools/` находятся команды для работы с калькулятором, сборки прошивки
и создания собственных программ. Профилирование, исследования и генераторы
штатных ресурсов находятся в [`dev/tools`](../dev/tools/README.md), общие
внутренние модули — в [`dev/lib`](../dev/lib/README.md).

## Устройство и прошивка

| Команда | Назначение |
| --- | --- |
| `mkc.cmd` | Двухпанельный файловый менеджер: копирование, просмотр и работа с файлами устройства |
| `mk61-firmware.cmd` | Выбор профиля, сборка, DFU-загрузка, установка System и совместимого комплекта программ |
| `build-gcc.cmd` | Прямая сборка STM32F401/F411 собственным GCC SDK проекта |
| `mk61-arduino-board.cmd` | Установка проектных плат в Arduino IDE |
| `install_gcc_dependencies.ps1`, `install_gcc_dependencies.py` | Установка закреплённого GNU Arm GCC с проверкой SHA-256; Python-вариант работает без PowerShell |
| `install_arduino_dependencies.ps1` | Зависимости совместимого пути Arduino IDE |
| `build_picocalc.py` | Сборка прошивки Pico H; `--fetch-sdk` скачивает закреплённые зависимости |
| `build_picocalc_apps.py` | Сборка нативных APP для Pico H |
| `package_picocalc.py` | Упаковка проверенной прошивки и содержимого microSD в комплект PicoCalc |
| `sync_picocalc_clock.py` | Синхронизация часов PicoCalc |
| `build_urq_app.py` | Сборка URQ/URQUI для STM32 или URQ для PicoCalc, проверка размеров APP и стека |
| `qst2urq.py` | Конвертация QST/manifest и UTF-8 текстовых ресурсов в переносимый C2/R1 пакет |
| `build_urq_library.py` | Проверка каталога UrqW и воспроизводимая сборка двух CC0-адаптаций без JS |
| `vfat_diagnostic.py` | Расшифровка диагностики виртуального USB-диска |

Например, из корня проекта:

```sh
./tools/mkc.cmd --help
./tools/mk61-firmware.cmd --list-profiles
./tools/mk61-firmware.cmd --mcu f411 --profile classic-v3 --build
python3 tools/build_picocalc.py --fetch-sdk
python3 tools/build_picocalc_apps.py
python3 tools/package_picocalc.py
```

После «Собрать и прошить» инструмент ждёт последовательный порт и устанавливает
состав `System` текущей сборки. USB-диск для этого не требуется.
Профиль прошивки проверяется до изменения файлов; повторная установка доступна
через `--install-apps`. Пользовательские APP и остальные каталоги сохраняются.
На macOS/Linux используется Bash-клиент MKC с `arduino-cli`, Perl и `iconv`,
на Windows — PowerShell-клиент. Другие программы должны освободить порт.

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
python3 tools/program_bundle.py --bundle .build/firmware/picocalc-pico-h
```

[Подробности обновления и команды](../doc/design/Program-bundle-installation.md).

## Собственные приложения, программы и шрифты

| Команда | Назначение |
| --- | --- |
| `build_portable_app.py`, `build-portable-app.ps1` | Сборка APP на C/C++/Rust, ABI 6; STM32 и Pico H имеют отдельные целевые сборки |
| `build_system_app_bundle.py`, `build-system-app-bundle.ps1` | Подготовка согласованного каталога `/System` для выбранного STM32-профиля |
| `build_f401_bundle.sh` | Комплект F401 с System APP и пользовательским manifest |
| `build_fmk_font.sh` | Конвертация шрифтов в FMK |
| `build_fmk_from_ui_atlas.py` | Упаковка монохромного JSON-атласа в FMK без изменения пикселей |
| `font_preview_study.py` | Просмотр и сравнение монохромных шрифтов на компьютере |
| `program_pack.py` | Упаковка программы МК-61 в CRC32 + ZX0 для команды `load` |
| `build_mk61_program_pack.sh` | Сборка нативного упаковщика программ, используемого Python-обёрткой |

[Быстрый старт C/Rust](../doc/src/MK61s-mini-APP-Quickstart.md) ·
[Руководство C/C++](../doc/src/MK61s-mini-APP-Programming.md) ·
[SDK](../sdk/portable/README.md) · [FMK](../doc/src/MK61s-mini-FMK.md).

Калькуляторные `.bin` размером 5…4096 байт MKC копирует побайтно;
F3 показывает hex, F4 оставляет их доступными только для чтения.

## Диагностика USB-диска

При ошибке USB-диска экран показывает `USB E12xx`. После выхода из режима
диска команда `vlog` возвращает последнюю причину, например:

```text
VFAT v=1 code=1221 phase=3 flags=0 actual=7492 limit=1536 subject=524541444D45
```

Это `File too large`: файл `README` (поле `subject` — безопасный UTF-8 prefix,
закодированный hex) имеет 7492 байта при лимите 1536. Расшифровать запись или
целый сохранённый transcript можно командой
`python3 tools/vfat_diagnostic.py < terminal.log`. `phase`: 1 — session,
2 — cache, 3 — directory entry, 4 — chain, 5 — validate, 6 — prepare,
7 — apply, 8 — commit. В `flags` бит 0 означает возможность повторной попытки,
бит 1 — усечение имени. `vlog clear` очищает запись; успешный реальный импорт
тоже очищает её. Обычный выход из USB-диска без записи причину не стирает.
Wire version и номера причин заданы в `code/virtual_fat_diagnostic.hpp`;
неизвестные версии нельзя молча разбирать как версию 1.

## Внутренние реализации

Каталоги `.mkc`, `.mk61-firmware`, `.mk61-arduino-board`, `.mk61-gcc`,
`.mk61-dfu`, `.mk61-app` и `.fmk-font` — реализации пользовательских команд.
Их не нужно запускать вместо соответствующего лаунчера.

Общие кодеки, запечатывание прошивок и релизный контракт находятся в `dev/lib`.
Собранные утилиты и комплекты сохраняются в `.build`, отдельно от исходников.
