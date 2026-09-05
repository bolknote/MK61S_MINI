# MK61s System APP

Все пять системных модулей собираются в самостоятельные контейнеры ABI 3:
FOCAL, BASIC, WBMP, Markdown и CHIP‑8. Связывание с resident ELF больше
не требуется. Упаковщик выбирает меньший из ZX0 и ARM Thumb BCJ + ZX0.

Сборка отдельного модуля:

```sh
python3 tools/build_portable_app.py --system focal \
  --arm-toolchain-bin /path/to/arm-gcc/bin --output-dir .build/FOCAL
```

Значения `--system`: `focal`, `tinybasic`, `wbmp-viewer`, `markdown-viewer`,
`chip8`. Для компактного Markdown на символьном экране добавьте
`--text-only`. Графический Markdown также открывает WBMP; в таком комплекте
отдельный `WBMP.APP` не нужен. CHIP‑8 требует графического экрана.

Обычные сборщики GCC, Arduino CLI и плата Arduino IDE `MK61s F401 + APP`
собирают ABI 3 автоматически и выбирают подходящий вариант Markdown.
Имена и расположение файлов прежние: `/System/FOCAL.APP`, `BASIC.APP`,
`WBMP.APP`, `MARKDOWN.APP`, `CHIP8.APP`. Сначала установите прошивку с новым
загрузчиком, затем замените файлы в `/System`. При последующих обновлениях
совместимой прошивки пересборка APP не нужна.

API использует C-структуры с явными размерами полей; дисплей, раскладку
клавиатуры, C5, редактор, арифметику и общую память предоставляет прошивка.
Код занимает прежнее окно 20 КиБ SRAM. Программа и переменные FOCAL/BASIC
сохраняются отдельно от исполняемого образа при переключении модулей.

`system_apps/build.cmd -BuildPath ...` остаётся оболочкой для сборки комплекта:
из каталога берётся путь к компилятору. `-Graphics 0` выбирает текстовый
Markdown; при запуске из сборщика прошивки этот параметр передаётся сам.
`-PortableApps 0` включает прежний ABI 2. Только для него нужны точные
resident ELF/BIN, `--just-symbols` и исходные объединённые `*/main.cpp`.

Контракт и сборка обычных C/C++ приложений описаны в
[SDK](../sdk/portable/README.md), системный интерфейс — в
[System API](../sdk/portable/SYSTEM-API.md).
