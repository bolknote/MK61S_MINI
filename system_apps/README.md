# MK61s System APP

FOCAL, BASIC, WBMP, Markdown, CHIP-8, SETUP и USBDISK собираются в те же
перемещаемые контейнеры ABI 6, что и обычные APPLICATION. У них общий
SDK startup, публичные
таблицы API и сервисов, проверка контейнера, релокации, динамическое размещение,
MPU и вытесняемый кэш. Единственная особенность System APP — каноническое имя
в `/System` и отдельный `Kind`, по которому resident находит нужную роль.

Сборка отдельного модуля:

```sh
python3 tools/build_portable_app.py --system focal \
  --arm-toolchain-bin /path/to/arm-gcc/bin --output-dir .build/FOCAL
```

Значения `--system`: `focal`, `tinybasic`, `wbmp-viewer`, `markdown-viewer`,
`chip8`, `setup`, `usbdisk`. Для компактного Markdown на символьном экране добавьте
`--text-only`. Графический Markdown также открывает WBMP; в таком комплекте
отдельный `WBMP.APP` не нужен. CHIP-8 требует графического экрана.

Полный согласованный каталог создаёт общий сборщик:

```sh
python3 tools/build_system_app_bundle.py \
  --resident-elf .build/resident.elf \
  --compile-commands .build/compile_commands.json \
  --output-dir binary/profile/System \
  --graphics 1 --focal 1 --basic 1 --wbmp 1 --markdown 1 --chip8 0
```

Он всегда собирает обязательные `SETUP.APP` и `USBDISK.APP`,
извлекает из служебной INFO-секции
resident согласованные `HELP0.TXT` и `HELP1.TXT`, добавляет включённые роли и
атомарно заменяет только принадлежащие ему канонические файлы. Оболочка
`system_apps/build.cmd` делегирует этому же коду; GCC, Arduino и
`mk61-firmware` не имеют собственных реализаций упаковки System APP.

Имена остаются стабильными: `/System/FOCAL.APP`, `BASIC.APP`, `WBMP.APP`,
`MARKDOWN.APP`, `CHIP8.APP`, `SETUP.APP`, `USBDISK.APP`. После прошивки resident скопируйте
весь каталог `/System` из того же комплекта. ABI 2/3/4/5 намеренно не
исполняются; старые APP нужно один раз пересобрать.

В заголовке `load_address=0x20000000` — только виртуальная база линковки для
таблицы релокаций. Она не резервирует SRAM. При загрузке APP получает сверху
свободного динамического диапазона ровно `align32(image + data + bss)`; куча и
временные буферы занимают диапазон снизу. 20 КиБ — проверяемый максимум одного
образа, а не постоянно отведённая область. Неисполняемый кэш APP можно
вытеснить, после чего память немедленно возвращается общему пулу.

API использует C-структуры с явными размерами полей. Базовые функции находятся
в `mk61_app_api`; C6, редактор, диалоги, настройки, математика, runtime helpers,
workspace и scratch доступны любому APP через публичный `query_service`.
Системного закрытого API нет. Состояние языков хранится в отдельном workspace
и потому не зависит от адреса или вытеснения исполняемого образа.

Написание обычных C/C++ приложений описано в
[руководстве разработчика](../doc/src/MK61s-mini-APP-Programming.md),
контракт контейнера — в [SDK](../sdk/portable/README.md), сервисы — в
[общем API](../sdk/portable/APP-SERVICES.md). Исторические сравнения размеров
ABI 2/3/4 сохранены в `sdk/portable` только как отчёты, не как варианты сборки.
