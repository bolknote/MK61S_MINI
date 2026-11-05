# Исходные материалы игр Spectrum

Этот каталог содержит исходные архивы, авторские уведомления и закреплённый
каталог `catalog.json`. Он используется сборщиком и не копируется на устройство.

Готовый каталог для копирования — `programs/spectrum/`. В нём находится
только `GAMES.img`: FAT16-образ DivMMC на 32 МиБ с распакованными игровыми
файлами и SYS/BIN esxDOS 0.8.9. ZIP, README, JSON, отчётов и лицензий
в каталоге для устройства и внутри образа нет.

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

Скопировать содержимое `programs/spectrum/` в `apps/SPECTRUM/games/`
на microSD. В Spectrum APP открыть DivMMC (`I`), выбрать
`games/GAMES.img`, запустить машину (`R`), затем открыть NMI-браузер
esxDOS (`Esc`, `N`).

- Ianna: `IANNA/LOADER`.
- Cosmic Payback: `COSMIC/COSMIC.TAP`.
- ULAplus: `ULAPLUS/GAMES/`, демо: `ULAPLUS/DEMOS/`, палитры: `ULAPLUS/PALETTES/`.

Для TAP используются NMI-браузер или `.tapein` и `LOAD ""` в esxDOS.
ZIP эмулятор не открывает. ULAplus включается в Options APP. Демо с
Timex/HAM или эффектами внутри строки могут требовать ещё не реализованных
возможностей. Дисковый образ при подключении защищён от записи.

Имена в образе имеют формат 8.3. Соответствие исходным названиям находится
на компьютере в `.build/spectrum-library/image-index.json`.

## Сборка и распространение

Подготовить ZIP из готового образа, без сети и внешних файлов:

```sh
python3 -m tools.apps.spectrum.build_spectrum_library \
  --zip .build/spectrum-library/spectrum-games.zip
```

Пересобрать готовый образ из закреплённых архивов:

```sh
python3 -m tools.apps.spectrum.build_spectrum_library \
  --esxdos .build/spectrum-app/devices/esxdos089.zip \
  --zip .build/spectrum-library/spectrum-games.zip
```

Без `--esxdos` используется готовый `programs/spectrum/GAMES.img`, проверенный
по `runtime.json`. Spectrum APP при сборке копирует только этот образ
в свой каталог `games/`. Загрузка из сети при сборке библиотеки не выполняется.

В архиве распространения файл для SD находится в `apps/SPECTRUM/games/`.
Авторские уведомления и лицензии лежат отдельно в корневом каталоге
`licenses/SPECTRUM-GAMES/` этого ZIP; они остаются на компьютере.
Служебные manifest и index сохраняются только в `.build/spectrum-library/`.

```sh
python3 tests/spectrum_library_self_test.py \
  --folder programs/spectrum \
  --zip .build/spectrum-library/spectrum-games.zip
```

Проверка читает каждый игровой файл обратно из FAT16, сверяет байты и
проверяет уведомления в архиве распространения и отсутствие служебных файлов
на устройстве.

## Внутренняя проверка

По отдельному указанию пользователя временно сохранена Snow Trap Dizzy
в `.build/spectrum-hardware-tests/` и на тестовой microSD. После проверки
её нужно удалить. Копия отсутствует в этом каталоге, `GAMES.img` и ZIP.
Остальные игры без найденного разрешения удалены.
