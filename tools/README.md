# Инструменты MK61s

В корне `tools` находятся только поддерживаемые пользовательские команды:

- `mk61-firmware.cmd` — сборка, DFU-загрузка и установка System APP;
- `build-gcc.cmd` — каноническая прямая GCC-сборка STM32F401;
- `mk61-arduino-board.cmd` — установка платы `MK61s F401 + APP` в Arduino IDE;
- `mkc.cmd` — двухпанельный файловый менеджер устройства;
- `build_f401_bundle.sh` — F401-комплект с System и custom manifest APP;
- `build_system_app_bundle.py` — общий для F401/F411/Arduino сборщик
  канонического каталога `/System`;
- `build_portable_app.py` — C/C++/Rust SDK и сборщик всех видов APP: единый ABI 6
  с автоматическим выбором ZX0 или BCJ + ZX0; инструкция в
  [`sdk/portable/README.md`](../sdk/portable/README.md);
- `build_fmk_font.sh` — конвертер шрифтов FMK;
- `build_fmk_from_ui_atlas.py` — упаковка уже проверенного однобитного
  JSON-атласа в FMK без повторного рендеринга или изменения пикселей;
- `generate_highnoon_font.py` — воспроизводимая сборка узкого игрового
  `programs/games/High Noon/HighNoon.FMK`: базовый public-domain растр 3×5
  дополнен читаемыми русскими буквами шириной до пяти пикселей;
- `generate_eliza_doctor.py` — воспроизводимая компиляция оригинального
  сценария DOCTOR 1966 года в компактные таблицы точного ELIZA-движка;
  `--check` проверяет соответствие таблиц исходному сценарию;
- `generate_ui_fonts.py` — воспроизводимая сборка встроенных пропорциональных
  шрифтов UC1609 из проверенных растров; `--check` проверяет актуальность таблиц.
- `font_preview_study.py` — сравнение реальных монохромных растров шрифтов
  на компьютере; [инструкция](.fmk-font/README-preview.md).
- `build_mk61_module_pack.sh` — низкоуровневый ZX0-упаковщик APP.
- `build_mk61_program_pack.sh` — сборка нативного упаковщика больших программ
  МК-61 в бинарный формат CRC32 + ZX0 для `load <адрес> <путь.bin>`.
- `program_pack.py` — Python-обёртка с автоматической сборкой этого упаковщика:
  `python3 tools/program_pack.py raw-image.bin program.bin`.
- `seal-firmware.sh`, `seal-firmware.ps1` — post-link запечатывание и
  независимая проверка CRC/content ID resident BIN для release-сборщиков.
- `release-contract.json` — версии зависимостей, профили и ресурсные бюджеты
  всех release/capability-сборок; `release_contract.py` проверяет контракт,
  выдаёт cases сборщикам и формирует отчёты по ELF и запечатанному BIN.
- `install_arduino_dependencies.ps1` — установка зависимостей из этого же
  контракта на Linux, macOS и Windows.
- `vfat_diagnostic.py` — расшифровка числовой причины `vlog` на компьютере;
  словарь объяснений не занимает Flash микроконтроллера.

Как написать и собрать своё приложение:
[короткий Hello World на C и Rust](../doc/src/MK61s-mini-APP-Quickstart.md) и
[полное руководство по C/C++ APP](../doc/src/MK61s-mini-APP-Programming.md).

Полный локальный выпуск проверяется `tests/run_release_preflight.sh`. GitHub
Actions вызывает те же repository-owned матрицы. При добавлении профиля или
изменении лимита сначала обновляется контракт, а не отдельный workflow.
Каждый case сохраняет JSON/Markdown с секциями, статической RAM, резервом
heap/stack, максимальным frame и крупнейшими символами. Адреса build-каталогов
и время генерации в сравнении отчётов не участвуют.

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

Каталоги с точкой в имени — внутренние реализации этих команд. Они не являются
дополнительными способами собрать одну и ту же прошивку:

- `.mk61-gcc` — общий F401 GCC-бэкенд;
- `.mk61-firmware`, `.mk61-arduino-board`, `.mkc` — реализации публичных
  полиглотных лаунчеров;
- `.mk61-app` — общий APP linker script, нативный упаковщик и ZX0-кодек;
- `.mk61-firmware-seal` — единая C++-реализация post-link sealer;
- `.fmk-font` — исходники конвертера, экспортёра и исследования FMK.

Скомпилированные host-утилиты кэшируются в `.build/tools`, а не рядом с
исходниками. Каталог `.build` можно удалить целиком без потери исходных данных.
