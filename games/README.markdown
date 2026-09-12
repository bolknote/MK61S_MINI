# Игры MK61

Каждая игра МК-61 находится в отдельной папке: `autoexec.m61`,
`manual.md` и иллюстрации `.wbmp`. Скопируйте нужную папку целиком в `games`
на USB-диске MK61S. Вход в неё через Проводник открывает памятку;
`LEFT`/`RIGHT` листают, `OK` или `ESC` закрывает её и запускает программу.

На графическом экране памятка содержит картинки; LCD1602 показывает текст
и подписи к изображениям. Отдельный WBMP можно открыть из Проводника;
изображения выше экрана доступны с прокруткой. Тексты помещаются в 1536 байт,
каждое изображение — в 1600 байт.

## Каталог

| Папка | Игра и памятка | Иллюстрация |
| --- | --- | --- |
| `Lunolet 1` | [Лунолёт-1](<Lunolet 1/manual.md>) — взлёт и мягкая посадка | Корабль и схема тяги, «ТМ», 1985 №6 |
| `Bumblebee Fly` | [Полёт шмеля](<Bumblebee Fly/manual.md>) — полёт по дому | Разрез и план дома, «ТМ», 1988 №3 |
| `Infinity Story` | [Бесконечная история](<Infinity Story/manual.md>) — путешествие по Фантазии | Фрагмент журнальной карты, «ТМ», 1988 №1 |
| `Fox Hunting` | [Охота на лис](<Fox Hunting/manual.md>) — пеленгация девяти лис | Историческая схема, «Наука и жизнь», 1990 №10 |
| `Naval Battle` | [Морской бой](<Naval Battle/manual.md>) — поединок с ПМК | Новая схема поля с однопалубными кораблями |
| `Wumpus` | [Вампус](Wumpus/manual.md) — охота в пещере | Рисунок из The Best of Creative Computing, 1976, и схема переходов |
| `Chase HQ` | [Chase H.Q.](<Chase HQ/manual.md>) — погоня за Ferrari | Новая схема дороги и обозначений |
| `Samurai` | [Самурай](Samurai/manual.md) — спасение принцессы Лу | Новая схема символов и управления |
| `Mult Lunolet` | [Космический мультфильм](<Mult Lunolet/manual.md>) — возвращение с Луны | Новая схема маршрута L → C → 3 |
| `Bumblebee` | [Шмель](Bumblebee/manual.md) — символьная анимация 16×2 | Схема двух направлений по кадрам M61 |
| `Pogonya` | [Погоня](Pogonya/manual.md) — поиск мафиози в городе | Рисунки из «Экспресса», 1991 №8 |

Авторство, ссылки на публикации, происхождение картинок и отличия конкретных
листингов записаны в [SOURCES.markdown](SOURCES.markdown). Полноразмерные
фрагменты иллюстраций и исходники новых схем — в
[doc/game-artwork](../doc/game-artwork/); этот каталог на калькулятор не копируется.

## Перед запуском

Для «Полёта шмеля» заранее выберите `ГРД`; для «Вампуса» — `Р`;
для «Самурая» `Р` выбирает Чёрного Ветра, а `ГРД`/`Г` — других героев.
Выбирать режим нужно на экране калькулятора до открытия папки:
внутри просмотрщика Markdown угловые клавиши не меняют режим.

У динамических игр и мультфильма сначала используйте обычную скорость
эмуляции (`CLASSIC`): ускорение сокращает время для чтения мерцающих кадров
и двухфазного управления шмелём.

К прежнему содержимому каждого `.m61` добавлена только первая строка
`open manual.md`; байты программ, регистры, подготовительные программы и
команды запуска сохранены. Старые отдельные `.m61` перенесены в
`<папка>/autoexec.m61`. Для новой попытки повторно войдите в папку, если в
памятке не указан другой способ.

Исторические сценарии начинают подготовку с `reinit`, сохраняя гарантию
чистых регистров старого встроенного загрузчика. Эта команда сохраняет
внешний режим углов. У демонстрации `Bumblebee` прежний запуск без `reinit`.

В прежних загрузчиках `Wumpus` и `Bumblebee` есть физические scan-code
`kbd E` и `kbd 04`, рассчитанные на mini/40TH. На Classic заранее выберите
`Р` для Wumpus и `Г` для Bumblebee. Эти команды и различия раскладок здесь
не изменялись. Во время полёта шмеля `Р` разворачивает `8000-` влево,
`Г` — `-0008` вправо; кадр удерживается командой `wait 200`.

`pacman-120x28.wbmp` — самостоятельная тестовая картинка, а не игра.
CHIP-8 ROM ниже остаются отдельными `.ch8`: эта упаковка относится к МК-61.

## CHIP-8 ROMs

The CHIP-8 console opens unmodified `.ch8` ROMs from any C5 directory. Copy a
base CHIP-8 ROM of up to 3584 bytes to the `MK61S C5` disk and open it in
Explorer.

The console uses C5 type magic `C1`; those bytes are not added to the ROM.
Screen compatibility, the full 0-F key map and game aliases are documented in
[`MK61s-mini-CHIP8.md`](../doc/src/MK61s-mini-CHIP8.md).

Four ready-to-run examples are included:

- `fuse.ch8` — **Fuse** by John Earnest, 424 bytes. Use CHIP-8 keys
  `5/7/8/9` to move and `6` to place a piece.
- `br8kout.ch8` — **Br8kout** by SharpenedSpoon, 199 bytes. Use CHIP-8 keys
  `7` and `9` to move the paddle.
- `space-invaders.ch8` — **Space Invaders v0.9** by David Winter, 1283 bytes.
  Use `4/6` (or `Left/Right`) to move and `5` (or `OK`) to start and fire.
- `echo8.ch8` — **ECHO-8**, an original first-person story game, 2039 bytes.
  Use `2/8` to move, `4/6` to turn and `5` to interact; see
  [`examples/chip8/ECHO-8`](../examples/chip8/ECHO-8/) for the spoiler-free
  manual and source.

Their SHA-1 values are respectively
`0cd895dc3d489d0e40656218900a04310e95f560` and
`31fc1c53cc610a9f4b9c5705c5a0f33fc028d123`, while Space Invaders is
`f100197f0f2f05b4f3c8c31ab9c2c3930d3e9571`. ECHO-8 is
`751fc6d702d83ab930a622f8fe4a078d18f74b48`.

The SHA-1 value of `pacman-120x28.wbmp` is
`c11baa9b3207fa89657d4545a0d2b6643fea0256`.
