# Сборка F401/F411 без пакета STM32duino

Обычная сборка resident, System APP и пользовательских manifest APP использует
GNU Arm GCC, CMake и Ninja. Установленные STM32duino, CMSIS package, Arduino
CLI, platform.txt, boards.txt и каталоги Arduino-библиотек не участвуют.

## Зависимости

В `third_party/stm32f4` сохранены 46 реально используемых заголовков и пять
лицензий: CMSIS Core 6.2.0, определения F401/F411, нужные ST HAL/LL-типы,
USB-декларации и шесть прежних USB interface-заголовков. Их байты взяты из
ранее проверенного набора и сохранены без изменения ABI. Manifest содержит
происхождение и SHA256 каждого файла; Python, PowerShell и CMake проверяют
его до компиляции. Git не преобразует переводы строк этих файлов; отдельный
тест делает свежий checkout с `core.autocrlf=true` и сверяет весь SDK.
Реализации Arduino Core, HAL и CMSIS-DSP не собираются.
Все компилируемые реализации находятся в проекте.

GNU Arm `14.2.1-1.1` устанавливается отдельно:

```powershell
pwsh -NoProfile -File tools/install_gcc_dependencies.ps1
./tools/build-gcc.cmd -Mcu f411 -Profile classic-v3
./tools/build-gcc.cmd -Mcu f401 -Profile mini-v3-a00
```

На Windows достаточно `powershell.exe` 5.1. Установщик выбирает официальный
xPack-архив по ОС/архитектуре, проверяет закреплённый SHA256 до распаковки и
версию компилятора до публикации каталога. Поддерживаются
`-ArchivePath` для офлайн-установки и `-InstallRoot`. Повреждённый архив не
оставляет установленного toolchain или временного staging-каталога.

Выбор компилятора: явный `-ToolchainPath`/`--toolchain`, затем
`MK61_GCC_TOOLCHAIN`, проектный `.build/toolchains`, затем `PATH`.
Поиска в Arduino15 нет. SDK по умолчанию находится в репозитории;
`-SdkPath`/`--sdk` и `MK61_GCC_SDK` выбирают другую проверяемую копию.
CMake 3.21+ и Ninja устанавливаются отдельно. На macOS/Linux нужны также
PowerShell, Python 3 и host C++17 для APP-паковщика. Обычная Windows-сборка
использует PowerShell/.NET без Python и host C++.

## Общие сборщики

Оба frontend `mk61-firmware.cmd` вызывают общий native-бэкенд для F401/F411.
Путь `MK61_APP_MANIFESTS` тоже переведён на GCC; его дополнительные зависимости —
Bash, Python 3 и host C++17. В CI release и production STOP больше не
используют Arduino CLI; resource contract и числовые бюджеты сохранены.

LTO-барьеры core/CDC и GNU ld `--wrap` задаются в CMake. ELF-проверки находят
binutils рядом с фактическим компилятором, а не в установленном пакете плат.
GNU stack note выставляется и для обычных, и для LTO-объектов; это
метаданные ELF, не изменение кода Flash.

Arduino IDE остаётся отдельным совместимым способом сборки. Её проверки
в CI выделены в отдельные задания и не являются зависимостями публикации.
`tests/run_release_preflight.sh` включает их только при
`MK61_ARDUINO_COMPAT=1`. Windows DFU-загрузчик пока использует прежний
Arduino recipe с STM32CubeProgrammer; команда сборки от него не зависит.

## Проверки 2026-10-16

Все 16 release/capability-конфигураций F411, две production STOP и девять
product/capability-конфигураций F401 прошли с запрещённым чтением каталогов
`~/Library/Arduino15`, `~/.arduino15` и `~/Library/Arduino`. Arduino CLI
указывал на отсутствующий файл, прежняя Core-переменная — на отсутствующий
каталог. Проверены фактические C/C++/ASM-команды, Ninja header dependencies,
отсутствие внешних реализаций и runtime-архивов, CRC, APP ABI/RAM, Flash,
стек, USB receive/wrappers, startup, RTC и политика STOP.

Для обоих MCU отдельно собран комплект с пользовательским `HELLO.APP`;
на F411 проверен встроенный USB-диск, на F401 — `USBDISK.APP`.
Межплатформенные проверки RAM WS0010 дали дельты 8/216/0/8 байт при
порогах 8/256/8/16; лимиты не увеличивались.

Контроль собран старым native GCC-бэкендом с установленными заголовками
STM32duino. Окончательный вариант — новым SDK и компилятором, скачанным
новым установщиком. Compiler version, feature-флаги и `SOURCE_DATE_EPOCH`
одинаковы. Полные BIN и десять файлов System F401 совпали побайтно:

| Контрольная конфигурация | Flash, байт | Статическая RAM, байт | Δ Flash | Δ RAM |
|---|---:|---:|---:|---:|
| F411 Classic V3 UC1609, полный native профиль | 375144 | 21584 | 0 | 0 |
| F411 mini V3 A00, полный native профиль | 349216 | 20032 | 0 | 0 |
| F401 mini V3 A00, native APP профиль | 235004 | 27652 | 0 | 0 |

RAM — сумма `.data + .bss + .noinit`. Это сравнение одинаковых native
конфигураций до/после переноса SDK, а не сравнение разных feature-наборов
или Arduino recipe с другими флагами. Код прошивки в `code/` не менялся.

Полный host-набор пройден через `tests/run_ci_strict.sh`:
Clang 18 проверяет переносимость, системный Clang — ASan/UBSan.
Тестовые скрипты DWT и mixed cache теперь соблюдают общий переключатель
`MK61_TEST_SANITIZERS`, поэтому первый проход не запускает несовместимый
с текущим macOS runtime ASan LLVM 18; второй сохраняет sanitizers.

Локально проверен macOS arm64; независимые Windows/Linux-сборки и Windows
без Python/host C++ добавлены в CI. Машинный отчёт с SHA256:
[stm32-independent-sdk-20261016.json](../measurements/stm32-independent-sdk-20261016.json).
