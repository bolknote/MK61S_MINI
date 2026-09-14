# Совместимость исходников System APP

Отдельного System API в исполняющей модели больше нет. Канонические FOCAL,
BASIC, WBMP, Markdown, CHIP-8 и SETUP — обычные перемещаемые APP ABI 5. Они
получают тот же `mk61_app_api`, вызывают тот же публичный `query_service` и
проходят тот же startup, loader, MPU и кэш, что `kind=APPLICATION`.

Файл `code/loadable_system_api.h` сохранён только как слой совместимости
исходников существующих адаптеров. Он включает публичный
`loadable_app_services.h` и задаёт механические алиасы:

- `mk61_system_api` → `mk61_app_services`;
- `MK61_SYS_*` → соответствующие `MK61_SERVICE_*`;
- `mk61_system_*` → соответствующие публичные `mk61_service_*`.

Новой APP следует напрямую подключать `mk61_app.h` и
`loadable_app_services.h`. Полный контракт описан в
[общем API приложений](APP-SERVICES.md).

## Единая точка входа

`sdk/portable/start.c` владеет `mk61_module_entry` для любого вида APP.
Команда `INITIALIZE` передаёт:

1. `argument0` — указатель на `mk61_app_api`;
2. `argument1` — CRC исходного образа;
3. `argument2` — публичный `enum mk61_app_kind`;
4. `argument3` — ноль, зарезервированный для append-only расширения.

Startup проверяет API, сохраняет `mk61_api`, `mk61_app_image_crc` и
`mk61_app_current_kind`, после чего вызывает необязательный
`mk61_app_initialize()`. Остальные команды направляются в
`mk61_app_command()`. Слабая реализация этого hook вызывает `main()` для RUN и
`mk61_app_open_file(id)` для FILE_OPEN, поэтому простому приложению не нужно
знать внутренний командный протокол.

System-адаптеры переопределяют те же hooks, но не имеют особой точки входа.
`sdk/portable/system/system_compat.cpp` переводит существующие интерфейсы
FOCAL/BASIC/просмотрщиков в вызовы публичной таблицы сервисов.

## Поиск и жизненный цикл

`kind=APPLICATION` получает inode выбранного файла. System kind сначала
разрешается в каноническое имя `/System/*.APP`. После этого путь полностью
общий:

`header → CRC → dynamic allocation → ZX0/BCJ → relocations → BSS → MPU → INITIALIZE → command`.

Одинаковый inode и заголовок повторно используют один opportunistic cache;
поведение `.data`/BSS не зависит от Kind. Когда нижнему staging-буферу или
другому APP нужна RAM, неисполняемый кэш можно вытеснить. Активный вызов не
вытесняется.

Языковое состояние FOCAL/BASIC хранится отдельно через публичный MEMORY
service в persistent workspace. Поэтому оно переживает вытеснение кода и не
содержит адресов внутри перемещаемого APP.

## Память без резерва

Resident linker экспортирует `__mk61_dynamic_begin` сразу после `_end` и
`__mk61_dynamic_end` перед стековым guard. Он не создаёт секцию или массив под
APP. Куча и staging растут снизу, APP получает сверху ровно
`align32(memory_size)`. Значение `0x20000000` в контейнере — виртуальная база,
по которой линковался образ; loader прибавляет дельту фактического адреса ко
всем `R_ARM_ABS32` из компактной таблицы релокаций.

Порог 20 КиБ — максимальный `image + data + bss` одного контейнера. Это
валидационная политика и верхняя граница MPU, а не постоянно потерянные 20 КиБ
SRAM. Фактический свободный диапазон виден в ELF-проверке
`tests/check_app_memory_elf.py`: `reserve=0` обязательно.

## Сборка

Один APP:

```sh
python3 tools/build_portable_app.py --name HELLO \
  --source examples/portable-apps/HELLO/main.c \
  --arm-toolchain-bin /path/to/arm-gcc/bin \
  --output-dir .build/HELLO
```

Одна System-роль использует тот же builder с `--system focal` (или другой
ролью). Полный `/System` создаёт `tools/build_system_app_bundle.py`; все
фронтенды F401/F411 и Arduino делегируют ему.

ABI 2/3/4 и прямые resident imports удалены из product path. Их размеры и
аппаратные прогоны сохранены только как исторические отчёты:
[SIZE-COMPARISON](SIZE-COMPARISON.md),
[RELOCATION-RESULTS](RELOCATION-RESULTS.md),
[HIL ABI 4](HIL-ABI4-2026-09-06.md).
