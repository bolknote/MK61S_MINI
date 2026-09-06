# Документация проекта

Редактируемые исходники находятся в `src/`. Каждый `src/NAME.md` собирается
в отдельный `NAME.pdf` в этом каталоге. PDF из таблицы ниже пересобраны
06.09.2026 из текущих Markdown-исходников.

| Руководство | Исходник | PDF |
| --- | --- | --- |
| Написание самостоятельных APP на C/C++ (ABI 3) | [Markdown](src/MK61s-mini-APP-Programming.md) | [PDF](MK61s-mini-APP-Programming.pdf) |
| Прежняя manifest-сборка APP (ABI 2) | [Markdown](src/MK61s-mini-APP.md) | [PDF](MK61s-mini-APP.pdf) |
| F401 и System APP в Arduino IDE | [Markdown](src/MK61s-mini-Arduino-IDE.md) | [PDF](MK61s-mini-Arduino-IDE.pdf) |
| Терминал | [Markdown](src/MK61s-mini-Terminal.md) | [PDF](MK61s-mini-Terminal.pdf) |
| Файловый менеджер MKC | [Markdown](src/MK61s-mini-MKC.md) | [PDF](MK61s-mini-MKC.pdf) |
| Аппаратные платформы и профили | [Markdown](src/MK61s-mini-Hardware.md) | [PDF](MK61s-mini-Hardware.pdf) |
| OLED1602 WEH001602A/WS0010 | [Markdown](src/MK61s-mini-WS0010.md) | [PDF](MK61s-mini-WS0010.pdf) |
| USB-экран и desktop-клиент | [Markdown](src/MK61s-mini-USB-Screen.md) | [PDF](MK61s-mini-USB-Screen.pdf) |
| Хранилище C5 и USB FAT12 | [Markdown](src/MK61s-mini-Storage.md) | [PDF](MK61s-mini-Storage.pdf) |
| Часы RTC | [Markdown](src/MK61s-mini-RTC.md) | [PDF](MK61s-mini-RTC.pdf) |
| FOCAL | [Markdown](src/MK61s-mini-FOCAL.md) | [PDF](MK61s-mini-FOCAL.pdf) |
| TinyBASIC | [Markdown](src/MK61s-mini-TinyBASIC.md) | [PDF](MK61s-mini-TinyBASIC.pdf) |
| Сценарии M61 | [Markdown](src/MK61s-mini-M61.md) | [PDF](MK61s-mini-M61.pdf) |
| Команда trap M61 | [Markdown](src/MK61s-mini-M61-Trap.md) | [PDF](MK61s-mini-M61-Trap.pdf) |
| Консоль CHIP-8 | [Markdown](src/MK61s-mini-CHIP8.md) | [PDF](MK61s-mini-CHIP8.pdf) |
| Изображения WBMP | [Markdown](src/MK61s-mini-WBMP.md) | [PDF](MK61s-mini-WBMP.pdf) |
| Просмотр Markdown | [Markdown](src/MK61s-mini-Markdown.md) | [PDF](MK61s-mini-Markdown.pdf) |
| Формат растровых шрифтов FMK | [Markdown](src/MK61s-mini-FMK.md) | [PDF](MK61s-mini-FMK.pdf) |
| Генератор случайных чисел | [Markdown](src/MK61s-mini-Random.md) | [PDF](MK61s-mini-Random.pdf) |
| API перехвата внешних команд по opcode | [Markdown](src/MK61s-mini-Command-Hooks.md) | [PDF](MK61s-mini-Command-Hooks.pdf) |
| API наблюдения и подмены ROM-команд | [Markdown](src/MK61s-mini-ROM-Hooks.md) | [PDF](MK61s-mini-ROM-Hooks.pdf) |
| Проверка оптимизаций ядра | [Markdown](src/MK61s-Core-Verification.md) | [PDF](MK61s-Core-Verification.pdf) |

Три первоначальные инструкции доступны только в PDF; редактируемых
исходников для них в репозитории нет, поэтому они не входят в автоматическую
пересборку:

- [Общее описание проекта](MK61s-mini-Documentation.pdf).
- [Инструкция по сборке устройства](MK61s-mini-Assembly.pdf).
- [Инструкция по прошивке микроконтроллера](MK61s-mini-Programming.pdf).

Дополнительные материалы:

- [Размеры APP до и после переноса](../sdk/portable/SIZE-COMPARISON.md):
  файлы, SRAM, resident и отдельный выигрыш BCJ.
- [Сжатие C5](design/C5-ZX0-compression.md): формат RAW/ZX0,
  `read_range`, large storage и переход FONT на raw-only FMK2.
- Иллюстрации руководства по терминалу: `src/assets/terminal/`.

## Сборка PDF

Из корня репозитория:

```sh
python3 doc/build_md_pdf.py
```

Скрипт автоматически находит все `doc/src/*.md`. Для сборки одного руководства:

```sh
python3 doc/build_md_pdf.py doc/src/MK61s-mini-APP-Programming.md
```

Нужны Python 3 и пакет `reportlab`, а также один из поддерживаемых шрифтов
с кириллицей (Arial в macOS или DejaVu Sans в Linux). Сборщик создаёт PDF
через временный файл и заменяет предыдущую версию после успешной сборки.
Оглавления с локальными ссылками на разделы сохраняют рабочие PDF-переходы.
Короткие блоки кода остаются на одной странице; длинные листинги могут
продолжаться на следующей. Иллюстрации сохраняют подпись на той же странице.

Проверка PDF-сборщика, дополнительно требующая `pypdf`:

```sh
python3 tests/doc_pdf_self_test.py
```

Для визуальной проверки страниц рекомендуется Poppler (`pdftoppm`).
