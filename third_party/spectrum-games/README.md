# Исходные материалы игр Spectrum

В Git хранятся только инструкции, авторские уведомления и закреплённый
каталог `catalog.json`. Игровые ZIP и `programs/spectrum/GAMES.img` скачиваются
и собираются локально; они исключены из Git. Этот каталог не копируется на устройство.

После загрузки `programs/spectrum/` содержит `GAMES.img`. Это FAT16-образ
DivMMC на 32 МиБ с игровыми файлами и SYS/BIN esxDOS 0.8.9.

## Состав

| Игра / коллекция | Разрешение |
| --- | --- |
| The Sword of Ianna 1.1, ESXDOS | Apache 2.0; оригинальная лицензия и авторство в `ianna/` |
| ULAplus 10th Anniversary Collection | 337 игровых TAP, 20 демо, 50 палитр; разрешения издателей внутри исходного архива |
| Cosmic Payback, YRGB 2020 | Авторское freeware-разрешение распространять неизменённую программу |

Игра или набор на PicoCalc ещё не проверялись. В исходных ZIP игровые
байты сохранены без изменений. Для всей дополнительной коллекции действуют
бесплатное некоммерческое распространение и сохранение авторских уведомлений.
Подробности проверки: [LICENSE-AUDIT.md](LICENSE-AUDIT.md).

## Запись на SD и запуск

Установите эмулятор в `/Programs/Spectrum/`. В архиве дополнения папка
`Games/Spectrum Collection/` содержит `GAMES.img` и `Play.txt`.
Скопируйте `Games/` в корень microSD. В проводнике откройте
**Игры → Spectrum Collection** и нажмите Enter. В эмуляторе откройте
NMI-браузер esxDOS (`Esc`, `N`).

- Ianna: `IANNA/LOADER`.
- Cosmic Payback: `COSMIC/COSMIC.TAP`.
- ULAplus: `ULAPLUS/GAMES/`, демо: `ULAPLUS/DEMOS/`, палитры: `ULAPLUS/PALETTES/`.

Для TAP используются NMI-браузер или `.tapein` и `LOAD ""` в esxDOS.
ZIP эмулятор не открывает. ULAplus включается в Options APP. Демо с
Timex/HAM или эффектами внутри строки могут требовать ещё не реализованных
возможностей. Дисковый образ при подключении защищён от записи.

Имена в образе имеют формат 8.3. Соответствие исходным названиям находится
на компьютере в `.build/spectrum-library/image-index.json`.

## Загрузка и сборка

Из корня репозитория выполнить:

```sh
python3 -m tools.apps.spectrum.fetch_spectrum_games
```

Скрипт получает Ianna из закреплённого выпуска, ULAplus с авторской страницы
itch.io, Cosmic Payback с YRGB и esxDOS из закреплённой ревизии. Проверяет
SHA-256 исходников, каждого игрового файла и итоговых ZIP, затем собирает
локальный `programs/spectrum/GAMES.img`. Существующие архивы сверяются без
повторного скачивания; несовпадение контрольной суммы останавливает работу.
Для загрузки только архивов есть `--archives-only`. Нужен Python 3, без
сторонних пакетов. Изменение или недоступность внешнего источника приводит
к явной ошибке, контрольные суммы автоматически не обновляются.

При сборке APP для нужного дерева microSD передайте `--with-games` и
`--games-output "путь/к/Games/Spectrum Collection"`. По умолчанию APP
собирается без игровых данных.

После первой загрузки можно подготовить архив для SD без сети:

```sh
python3 -m tools.apps.spectrum.build_spectrum_library \
  --zip .build/spectrum-library/spectrum-games.zip
python3 tests/spectrum_library_self_test.py \
  --folder programs/spectrum \
  --zip .build/spectrum-library/spectrum-games.zip
```

В архиве файлы для SD находятся в `Games/Spectrum Collection/`, уведомления —
в `licenses/SPECTRUM-GAMES/`. Служебные manifest и index сохраняются только
в `.build/spectrum-library/`. Проверка читает каждый файл обратно из FAT16
и сверяет исходные байты. Игровые архивы, образ и ZIP для SD не коммитить.

## Внутренняя проверка

По отдельному указанию пользователя временно сохранена Snow Trap Dizzy
в `.build/spectrum-hardware-tests/` и на тестовой microSD. После проверки
её нужно удалить. Копия отсутствует в этом каталоге, `GAMES.img` и ZIP.
Остальные игры без найденного разрешения удалены.
