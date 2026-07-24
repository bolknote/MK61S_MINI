# MK61s F401 + APP в Arduino IDE

Версия документа: 24.07.2026

Эта инструкция собирает через обычные кнопки Arduino IDE согласованный
комплект для STM32F401CC:

```text
binary/mk61s-M-mini-v3-lcd1602-a00-f401/
├── mk61s-M-mini-v3-lcd1602-a00-f401.bin
├── build.flags
├── build.apps
└── System/
    ├── FOCAL.APP
    ├── BASIC.APP
    └── WBMP.APP
```

Это именно штатные FOCAL, TinyBASIC и просмотрщик WBMP. Создавать
пользовательский `HELLO`, manifest `app.mk61` или менять прошивку для этого не
нужно.

## Зависимости

В Arduino IDE установите:

- Boards Manager: `STM32 MCU based boards` версии `2.12.0`;
- Library Manager: `LiquidCrystal` версии `1.0.7`;
- Library Manager: `STM32duino RTC` версии `1.9.0`.

Отдельный `arduino-cli` не требуется. На Windows не нужны Bash, `dfu-util` и
host-компилятор C++: сборка использует PowerShell и инструменты, входящие в
STM32 Core. Для Upload через DFU STM32 Core использует собственный
STM32CubeProgrammer recipe.

## Установка платы

Закройте Arduino IDE и из корня проекта выполните на macOS/Linux:

```bash
./tools/mk61-arduino-board.cmd
```

На Windows из `cmd.exe` или PowerShell:

```bat
tools\mk61-arduino-board.cmd
```

Это полиглотный launcher: в macOS/Linux он запускает shell-установщик, а в
Windows — PowerShell. Он копирует маленький пакет платы в стандартный
sketchbook и ничего не загружает из сети.

Если sketchbook перенесён из стандартного каталога:

```bash
./tools/mk61-arduino-board.cmd --sketchbook /path/to/Arduino
```

```powershell
tools\mk61-arduino-board.cmd -Sketchbook D:\Arduino
```

Проверить установку без изменения файлов:

```bash
./tools/mk61-arduino-board.cmd --check
```

```powershell
tools\mk61-arduino-board.cmd -Check
```

После обновления репозитория запустите установщик ещё раз: установленная плата
является копией служебных файлов. Затем запустите или перезапустите Arduino
IDE.

## Выбор профиля

1. Откройте файл `code/code.ino`. Это служебный основной tab Arduino; код
   прошивки остаётся в соседнем `mk61s-M.ino`.
2. В Board Selector найдите `MK61s F401 + APP`.
3. В меню Tools выберите платформу:
   `mini V3`, `mini V2`, `Classic V3`, `Classic V2` или `40th`.
4. Отдельно выберите экран:
   `LCD1602 · CGROM A00`, `LCD1602 · CGROM A02` или `UC1609`.
5. Выберите `APP` или `Выключен` для FOCAL, TinyBASIC и WBMP viewer.
6. При необходимости задайте USB-экран, расширенные настройки шрифта,
   быстрый Explorer и математический backend.

Допустимы только реальные сочетания:

| Платформа | Экран |
| --- | --- |
| mini V2/V3 | LCD1602 A00 или A02 |
| Classic V2/V3 | UC1609 |
| 40th | UC1609 |

Несовместимая пара останавливает сборку до запуска компилятора с понятной
ошибкой. Платформа и экран намеренно остаются двумя независимыми меню.

## Verify, Export и Upload

Обычный Verify выполняет всю сборку и создаёт каталог в `binary/`. Имя
каталога содержит выбранные платформу и экран. В нём лежат:

- `.bin` resident-прошивки;
- только включённые `System/FOCAL.APP`, `System/BASIC.APP`,
  `System/WBMP.APP`;
- `build.flags` с точными compile-time ключами.

Повторная сборка того же профиля удаляет из результата канонический System APP,
если его ключ был выключен. Другие каталоги и пользовательские APP сборщик
платы не трогает.

Upload сначала создаёт тот же комплект, затем прошивает через DFU только
resident `.bin`. Переведите BlackPill в системный DFU перед нажатием Upload.
APP нельзя записать в C5, пока устройство находится в DFU, поэтому установка
состоит из второго шага:

1. дождитесь запуска новой прошивки;
2. на MK61s откройте `Меню → USB-диск`;
3. на диске `MK61S C5` создайте `/System`, если каталога ещё нет;
4. скопируйте содержимое `System` из только что созданного комплекта;
5. выполните безопасное извлечение диска и только затем нажмите `ESC`.

Вместо USB-диска файлы можно скопировать правой панелью
`tools/mkc.cmd`. Не смешивайте resident и APP из разных сборок: заголовок
каждого APP содержит размер и CRC точного `.bin`, поэтому несовпадение
отклоняется как `app/firmware mismatch`.

## Почему IDE-контейнеры не ZX0

Автоматизированный `tools/mk61-firmware.cmd` запускает отдельные Arduino-сборки
с LTO и host-упаковщик ZX0. Для полностью ручного пути это потребовало бы
`arduino-cli`, Bash и отдельный C++17-компилятор на Windows.

Плата `MK61s F401 + APP` использует уже созданные Arduino IDE ARM-объекты,
отдельно связывает каждый System APP по фактическому адресу SRAM-overlay и
записывает payload `NONE`. Формат APP изначально поддерживает `NONE`; CRC,
привязка к resident, проверка размеров и ABI остаются теми же. Все три штатных
образа укладываются в 20 КиБ.

Если важен минимальный размер файлов C5, используйте
`tools/mk61-firmware.cmd`: результат будет ZX0. Если важна сборка одной кнопкой
в Arduino IDE без внешнего toolchain, используйте эту плату.

## Диагностика

| Сообщение | Что проверить |
| --- | --- |
| Плата не видна | Перезапустить IDE; повторить установщик с правильным sketchbook. |
| `LiquidCrystal.h: No such file` | Установить `LiquidCrystal 1.0.7` через Library Manager. |
| Не найден `STM32duino RTC` | Установить `STM32duino RTC 1.9.0`. |
| `incompatible platform/display pair` | Выбрать LCD для mini либо UC1609 для Classic/40th. |
| `does not fit the 20 KiB SRAM overlay` | Выбранный System APP вырос сверх лимита; это ошибка сборки, а не DFU. |
| `app/firmware mismatch` | Скопировать `System` из каталога того же Verify/Upload, что и resident. |
| Upload не находит устройство | Перевести STM32F401 в системный DFU и повторить Upload. |
