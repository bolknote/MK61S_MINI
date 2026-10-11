# C9: кеш чтения и ускорение USB

## Актуальный статус — 10.10.2026

Работа находится в `feature/flash-read-cache`, база `d12fc59d5`.
Отчёт фиксирует проверки 10.10.2026; изменения оформлены в коммит 11.10.2026.
Основной `plan-fat12.md` не менялся.
Поддерживается только C9, без миграций и читателей старых ФС.

Classic F411/UC1609/512 КиБ работает на **0ACCCFB9** (391796 байт).
Matched System установлен и побайтно проверен. Полный аппаратный тест PASS:
320 native пустых файлов,320 host файлов,1980 readbacks/146456 bytes,
прерванная загрузка,пять warm reset,delete/refill107 и cleanup=true.
Полный прогон374.61с;максимальная native-команда8.816с. Выход в CDC после
создания320 файлов9.452с,после delete/refill8.247с. VFAT0/staged0,CRASHnone,
IWDGreset0. Все30 Games/35480 bytes проверены перед и после теста.
Первое дополнительное чтение Games получило неполную строку CDC; полный
повтор чтения прошёл. Это сбой framing передачи, а не несовпадение payload.

Mini F411/A00/16 МиБ работает на **9A9A8F37** (339012 байт).
Matched System, coherence, BASIC и обычный USB с кириллическим LFN PASS.
Полный аппаратный повтор PASS: 320 native пустых файлов, 320 host файлов,
1980 readbacks / 146456 bytes, одна прерванная загрузка, пять warm reset,
delete/refill 107 и cleanup=true. Полный прогон 626.09 с; максимальная
native-команда 19.647 с (удаление всей тестовой ветки). После теста остался
только System. VFAT code 0 / staged 0, CRASH none, IWDG reset 0.
Выход в CDC после создания — 37.457 с, после delete/refill — 25.124 с.
Большой изменённый том mini по-прежнему требует длительного import;
ускорение read-only выхода не устраняет эту стоимость.

| Проверка | Результат | Лог в `/private/tmp` |
| --- | --- | --- |
| Clang18 + ASan/UBSan, storage/VFAT/fault/wear | PASS, оба прохода | `mk61-c9-checkpoint-final-ci.log` |
| F401 GCC release matrix | PASS,9 вариантов | `mk61-c9-checkpoint-qualified-f401-matrix.log` |
| F411 release matrix | PASS,16 вариантов | `mk61-c9-checkpoint-qualified-f411-matrix.log` |
| F401 Arduino UC1609 | PASS,free2060>=2048 | `mk61-c9-checkpoint-v8-arduino-f401.log` |
| F411 STOP | PASS,2 профиля | `mk61-c9-checkpoint-qualified-stop.log` |
| F411 O3 | PASS,free81316 | `mk61-c9-checkpoint-qualified-o3.log` |
| Stock linker F401/F411 | PASS | `mk61-c9-checkpoint-qualified-stock.log` |
| Cross-MCU RAM | PASS,4 прежних лимита | `mk61-c9-checkpoint-qualified-cross-ram.log` |
| ARM IRQ/OOM/lifetime,APP+stage | PASS,2 ELF | `mk61-c9-checkpoint-qualified-lifetime-arm.log` |
| ARM SETUP/viewers/compiler/VM/INPUT | PASS,3 адреса | `mk61-c9-checkpoint-qualified-{setup-arm,viewers-arm,app-flow}.log` |
| Classic coherence/BASIC/USB/full HIL | PASS | `mk61-c9-checkpoint-classic-{coherence,usb,full-hil}.log` |
| Games после Classic HIL | PASS после повторного чтения | `mk61-c9-checkpoint-classic-games-after-retry.log` |
| Mini coherence/BASIC/USB | PASS | `mk61-c9-checkpoint-mini-{coherence,usb}.log` |
| Mini full HIL | PASS | `mk61-c9-checkpoint-mini-full-hil.log` |
| Mounted data->sync->FAT/dirent | PASS,512КиБ и16МиБ | `mk61-c9-checkpoint-ci.log`, permanent regression |
| Replay System/Games +320 host | PASS,5 checkpoints/320 payloads | `mk61-classic-host-repro/final-policy.log` |

Промежуточный mounted import теперь сохраняет принятые data sectors,
которые ещё не связаны с FAT/dirent. На512КиБ foreground checkpoint
ограничивает журнал; IRQ читает только RAM и удерживает BOT packet до
service. После checkpoint повторно проверяется PVD. Окончательный close
по-прежнему освобождает orphan sectors. C9 layout и APP ABI не менялись.

Проверенный кеш чтения использует свободный OVERLAY; кеши распределения
проверяют CRC и уникальность владельцев. Ни один кеш не заменяет источник
истины и не увеличивает write/erase counts. В host workload bulk reads
снижены269510→22212 при тех же2732 mutations/90 erases. Кеши вытесняются
ради APP только в idle состоянии. Повторное чтение1536 bytes на платах
сократилось примерно с1.4мс до27–68мкс с неизменной CRC.

F411 WORKSPACE/BULK,VM cache и MSC transport выделяются в foreground,
сохраняют адрес до reset и запрещены в IRQ. Прежние объёмы и RAM limits
сохранены. После учёта будущих heap allocations остаётся43104 bytes наWS
и24736 наClassic; APP20480 иstage2560 помещаются. F401 буферы статические.

ROM reserve сохранён благодаря упаковке неизменных core instructions,
таблиц пикселей/метрик и общей обработке BOT. Все543 glyphs/24845 pixels
совпадают с исходными атласами. Документ `doc/MK61s-mini-Storage.pdf`
обновлён,все15 страниц визуально проверены; новый раздел staging настр.12.

UNMAP не реализуется и не объявляется: удаление известно через FAT import,
NOR sectors освобождает GC. Windows/Linux hardware не проверялись; доступен
macOS. Host: macOS 26.7.1 (25G241), arm64; штатный msdos/Fskit,
mount options `local,nodev,nosuid,noowners,noatime,fskit`. Fault/torn-write
модели и warm reset не выдаются за physical power cuts.

Проверка frozen-source manifest: все377 файлов code/SDK/build policy
совпадают с snapshot окончательного кандидата. Strict CI terminal exit0:
104 close cuts,504 torn reclaim cases,587 mutation cases/69 rejected;
VFAT builtin,module,proxy и stream PASS. Минимальные ROM/RAM reserves,
максимальный APP и прежние cross-MCU RAM budgets сохранены.


## Архив измерений и промежуточных итераций

Ниже сохранена история. Размеры образов, незакрытые gates и состояние
выполнявшихся процессов в ней относятся к указанной итерации; текущий
статус приведён в таблице выше.

Работа ведётся в `feature/flash-read-cache`, HEAD `d12fc59d5`. Изменения
не добавлены в индекс и не закоммичены. `plan-fat12.md` в основном checkout
остаётся отдельным незакоммиченным планом. Classic в этой фазе не прошивается.

Текущая mini: STM32F411, дисплей A00, NOR EF4018 16 МиБ, SPI 24 МГц,
MCU 96 МГц. Public ID `6FF33152484A4488`, USB `3688388E3233`.
На ней A00-сборка **D917095A** с согласованным и побайтно проверенным System.
Сужение RAM-таблицы staging загружено и проверено на устройстве.
Формат C9 не менялся; новых миграций или читателей старых ФС нет.

## Реализация

### Проверенный кеш файлов в RAM

`MK61_PROGRAM_STORE_READ_CACHE_BYTES`: по умолчанию 4096 для F411/host,
0 для F401. Кеш занимает свободную OVERLAY lease по фактическому размеру файла.
Он хранит полностью декодированные, проверенные CRC байты. Ключ включает
эпоху, физический адрес/длину записи, ID, родителя, длину, имя, тип и флаги.
Повторное чтение использует memcpy без NOR и ZX0. Большие файлы, streaming,
EOF и нехватка RAM используют обычный проверяемый путь. Любая попытка
физической записи/стирания инвалидирует кеш; init/format освобождают lease.

Кеш имеет низкий приоритет, не вытесняет APP для собственного заполнения.
APP-аллокатор может освободить простаивающий файловый/стейджинговый кеш
и повторить выделение памяти. Занятые lease и загружаемый APP защищены.
USB staging владеет OVERLAY, поэтому этот кеш ускоряет нативные чтения,
а улучшение USB выполняется отдельными изменениями ниже.

### Проверка неизменившегося дерева перед импортом

Сертификат применённого host-view зависит от catalog revision, а не от
поколения staging. Короткие FAT timestamps сравниваются отдельно от структуры;
каждый изменённый байт LFN остаётся структурным. USB callback сравнивает
только RAM, сравнение с постоянными CRC-секторами выполняется в foreground.
Непроверенный сектор не разрешает пользоваться устаревшей картой AppleDouble.

При пустом восстановленном журнале native projection уже представляет
каталог. Если хост изменил структуру FAT/dirents, существующие проходы
RESERVE/RESERVE_NAMES дополнительно проверяют семантическое равенство:

- каждый поддерживаемый узел совпадает по ID, имени, родителю, виду и типу;
- ID встречается ровно один раз, число узлов равно native catalog;
- длины и полные цепочки FAT совпадают;
- внутри видимых данных файлов нет staged-секторов.

Это позволяет обойти публикацию нового каталога, если macOS только создала
игнорируемый служебный каталог или обновила timestamps. Настоящее изменение,
дубликат, иной файл или цепочка оставляют полный validator/import. Mounted
SYNC сохраняет точные поддерживаемые host metadata; final close использует
существующий durable marker и восстановление после сбоя. Проверка
`MK61_C9_METADATA_PRECHECK` включена для builtin F411, выключена для F401
и внешней USBDISK.APP, которая сохраняет лимит загрузки 20 КиБ.

### Пакетирование сканирований AppleDouble

Исходный порог половины журнала приводил к полному сканированию при каждом
новом структурном пакете, когда обычные файлы уже занимали больше половины.
Диагностика на mini обнаружила 551 сканирование за создание 220 файлов:
305 из 421 секунд ушли на эти сканирования.

Первый scan по-прежнему начинается на половине журнала. После него следующий
порог учитывает оставшиеся live-записи и два объёма RAM-кеша. Верхняя граница
сохраняет запас для старого и нового пакетов, compaction segment и семи
свободных индексных записей. После mounted import порог пересчитывается по
уменьшившемуся журналу. Обмен по SPI в USB callback не добавлен.

Просто перенести первый scan к почти полному журналу оказалось хуже для
износа: плотные live-сегменты приходилось чаще копировать при compaction.
В окончательном варианте этот промежуточный подход заменён пакетированием.

### Сопутствующие ограничения

Общий LRU helper, известные длины расширений и устранение повторного LBA
lookup позволили сохранить USBDISK loaded 20476/20480 без увеличения лимита
или удаления форматов. VM image-cache начинается с нулевого BSS, исключая
недопустимый constructor до setup. Полные BASIC/FOCAL компиляторы явно
ограничены compiler/host/test ролями; resident INPUT/checksum сохраняются.
Это исправляет ложное переполнение анализа стека F401 без удаления
фактически поставляемой функциональности.

## Измерения

Одинаковый pinned mini A/B сценарий: 320 native пустых файлов, затем
220 однобайтовых файлов через macOS с fsync, readback, reset и уборка.
Счётчики NOR измеряют весь соответствующий MSC-сеанс.

| Вариант | Выход после чтения, с | Создание 220, с | Выход после записи, с | Стирания в сеансе записи |
| --- | ---: | ---: | ---: | ---: |
| 5C5A3A5F, диагностический исходный | 5.838 | 420.954 | 37.604 | 1024 |
| 3AA7B5BD, поздний первый scan | 1.980 | 225.047 | 29.080 | 1830 |
| **4470E457, адаптивные пакеты** | **2.013** | **140.191** | **29.922** | **1042** |

Последний вариант уменьшил flash reads в сеансе записи с 1,763,723 до
424,020, ускорив создание примерно втрое при близком исходному числе
стираний. Это не доказывает уменьшение износа относительно исходного варианта.
Каждый A/B прогон: PASS, 1400 CDC readbacks, 3 warm resets, cleanup.

Нативный кеш: на старом сопоставимом A/B RAW median1380→62 мкс, PACK1388→61
мкс. На новых образах cold1536-byte read около1.4мс, warm обычно26–53мкс.
Host-тесты: 128 случайных warm reads RAW/малого/большого ZX0 дают0 NOR reads
и0 decodes; disabled control сохраняет streaming/проверяемое чтение.

Модель native subdir timestamp:48507 reads/1355 mutations→14759/7.
Игнорируемый host каталог:1196 reads/11 mutations, native revision неизменна.
Настоящее изменение Guard корректно импортируется. Между пакетами при225
занятых staged-секторах0 SPI; при431 новый scan запускается до вытеснения.

## Проверки и артефакты

Строгая4470E457 A00:338412 bytes, max-frame1928, ROM/RAM/CRC/constructors
PASS. Tracked virtual_fat.cpp совпадает с сохранённым входом builder.
Matched System проверен на устройстве, hardware CRC valid.

- Полный ASan/UBSan VFAT builtin/module/proxy/stream corpus: PASS.
- 587 мутаций metadata,69 отказов;104 прежних и48 новых torn-close случаев: PASS.
- ARM compiler/VM/INPUT, DATA, cancel, retry, poisoned eviction,3 адреса: PASS.
- External USBDISK loaded20476, BSS366, container15244: PASS.
- ARM strcmp:1232 alignment/unsigned/NUL/read-bound/ABI случаев: PASS.
- 4470E457 cache/COW/rename/delete-recreate/cancel/BASIC/reset-readback: PASS.
- Полный hardware scenario4470E457: PASS,654 files,2296 readbacks/91728 bytes,
  107 delete/refill,Russian rename,6 warm resets,cleanup.
- Полный непрерывный CI Clang 18 + ASan/UBSan для 4470E457: PASS, exit 0.

В одинаковом большом654-file сценарии по сравнению с584D415D:

| Операция | До, с | 4470E457, с |
| --- | ---: | ---: |
| Создание320 файлов через macOS | 1420.295 | 291.603 |
| Выход после создания | 54.094 | 48.062 |
| Выход после107 замен и rename | 31.043 | 30.386 |
| Выход после чтения всех файлов | 8.775 | 2.581 |

После финального cleanup на mini остался только System. VFAT code0/staged0,
CRASH none, IWDG reset0; max command25.734s — массовый native cleanup.
Проверка подтверждает ускорение создания и read-only выхода; обычный импорт
и выход после реальных изменений всё ещё требуют30–48с.

Логи и JSON лежат в `/private/tmp` с префиксами:
`mk61-c9-mini-trace-hil`, `mk61-c9-batching-mini-ab-hil`,
`mk61-c9-adaptive-mini-ab-hil`, `mk61-c9-adaptive-mini-coherence`,
`mk61-c9-adaptive-mini-full-hil`, `mk61-c9-adaptive-app-flow`,
`mk61-c9-adaptive-ci`, `mk61-c9-adaptive-full-vfat`.
Строгие image/ELF/System: `/private/tmp/mk61-c9-adaptive-mini-output`.
Исходная хронология экспериментов сохранена в
`/private/tmp/mk61-c9-read-cache-experiment-log-2026-10-10.md`.

## Оставшиеся ограничения

Полный импорт новых файлов остаётся медленным: только APPLY в исходном
220-file trace занял17.056с, общий commit25.303с. Пакетирование исправляет
повторные сканирования, но не устраняет эту стоимость публикации каталога.

F401 Classic-v2 ROM reserve не проходит также в baseline main d12fc59d5:
260420/262144 bytes, свободно1724 при требовании4096. Предыдущие изменения
этой worktree добавляли44 bytes; данный baseline gate не закрыт и не ослаблен.

Физические power cuts и hardware Windows/Linux в этой фазе не проводились.
Torn-write модели и warm reset не подменяют такие проверки. UNMAP не
реализован и не рекламируется; FAT deletion и native GC остаются механизмами
освобождения. Production goal ещё не закрыт.

## Продолжение: кеши распределения C9 — 10.10

Предыдущий turn классифицирован как progress:4470E457 исходники, CI, ARM
и654-file HIL подтверждены; сравнение определило оставшуюся стоимость импорта.
Текущие требования сохраняются: production ФС поplan-fat12, обратная
совместимость не нужна, план не коммитить, работа в отдельной worktree, mini
F411/A00 прежде Classic. Общий production goal не закрыт.

Временная A00 диагностика4DC7F37B: pinned320/220 HIL PASS/cleanup. При импорте
220 новых файлов write_file_from_source17.689с; checkpoint9.877с, включая
allocate_catalog_sector9.505с иlive_sector_window4.290с; FAT occupancy5.877с
на225 вызовов. Суммы вложенных таймеров не складывать. Поиск имени и проверка
коллизии вместе1.183с. Диагностические исходники тольков/private/tmp, вfeature
не перенесены. Логиmk61-c9-import-profile-hil.json/.log.

НоваяMK61_C9_ALLOCATION_CACHE (F411/host1,F4010):
-511-byte bitmap уникальных FAT claims. Строится по всем валидным текущим
 inode/mapping с проверкой общего числа и дубликатов. WAL update снимает
 старые и добавляет новые claims; сбой чтения инвалидирует необязательный
 кеш. Удаление/release инвалидирует его лениво, сохраняя локальность удаления.
-512-byte bitmap физических live references для flash до16MiB. Один
 checkpoint повторно использует доказанный snapshot для нескольких COW
 аллокаций. Inode mutation/init/load/format инвалидируют; pending pages,
 root/WAL, pins, staging, current/reserve иlarge writer проверяются динамически.
 Большие flash используют прежний полный scan.

CRC исключаемого owner mapping проверяется заново: warm Plan не доказывает
целостность вновь читаемых cluster bytes. Новый corruption regression
воспроизвёл ошибку прототипа, затем подтвердил отказ до любых мутаций и
сохранность другого owner. Никакой on-flash версии, миграции или ABI не добавлено.

Модель320 новых файлов при320 native пустых:241244→22212 NOR reads,
mutations2732/erasures90 одинаковы. Owner transition/reboot PASS;32 torn-write
и34 read-failure точек PASS. Полные ASan/UBSan storage (обаCRC backends,F401/F411)
иVFAT builtin/module/proxy/stream,587 mutation corpus PASS.
Один первый private full-run взял старый/private/tmp/app_memory_acquire.inc
из-за quoted include в перемещённом test.cpp; harness исправлен на generated
include изbuild dir, затем весь полный корпус PASS. Исходники APP allocator
не менялись этим исправлением harness.

Код перенесён вfeature/flash-read-cache безstaging/commit. Строгий свежий
A00 образ, его matched System, новый непрерывный CI и физический A/B ещё
должны подтвердить аппаратный выигрыш; host10.8x не выдавать заhardware gain.

Строгая A00 сборкаA1495B32:339388 bytes (+976),max-frame1928; guarded
APP pool43112 вместо44144 (кеши и alignment стоят1032 bytes RAM). ROM/RAM/
CRC/constructors PASS. Код config/program_store/FAT-chain byte-exact к
сохранённому входу builder. Аппаратный A/B, ARM flow, внешний20-KiB module
и окончательный непрерывный CI выполняются. Устаревший прототипD5F08B19
с найденным corruption case на устройство не загружался.

A1495B32 pinned A/B320/220 PASS:1400 CDC readbacks,3 warm resets,cleanup.
Readonly2.264с;create220141.979с;write-eject22.365с (4470:29.922).
Весьwrite session flash.read300580 вместо424020, erases1051 вместо1042.
Создание практически неизменно; подтверждён выигрыш выхода послеизменений
при близком erase count. Нативный массовый cleanup max15.149с.
ARM compiler/VM/INPUT flow PASS; внешнийUSBDISK20476/20480 PASS.
Полный654-file HIL,cache/COW/BASIC coherence и final CI выполняются.
Логиmk61-c9-allocation-verified-{mini-ab-hil,app-flow,usbdisk,ci}.

Большой HIL A1495B32 подтвердил первое закрытие изменённого654-file дерева:
320 host files create~291с (практически4470), eject33.076с вместо48.062.
Повторное заполнение107 файлов ифинальная уборка ещё выполняются.
Coherence A1495B32 PASS:9 checks,RAW cold1419/warm51–54µs,COW/rename/
delete-recreate/cancel,BASIC numeric3 вызова,reset-readback.

Полный A1495B32 mini HIL завершён PASS:654 files,2296 readbacks/91728 bytes,
107 delete/refill,Russian rename,6 warm resets,cleanup. Create320293.399с
(4470:291.603), create-eject33.076с (48.062), refill-eject22.069с (30.386),
readonly2.903с (2.581). Native cleanup max19.197с (25.734).
Readonly не ускорился этим изменением; новый выигрыш относится к публикации
реальных изменений. VFATcode0/staged0,CRASHnone,IWDGreset0; толькоSystem.
Логиmk61-c9-allocation-verified-mini-full-hil.json/.log,exit0.
Полный final CI всё ещё выполняется; широкую production qualification
не считать завершённой поодному hardware PASS.

Финальный непрерывный CI A1495B32 завершён PASS,exit0: Clang18 + AppleClang
ASan/UBSan,оба CRC backends,allocation transitions/corruption/fault points,
storage/VFAT builtin/module/proxy/stream и587 metadata mutations.
Hardware A/B,full654/coherence,ARM flow,strict mini gates иexternal20KiB
такжеPASS. Файлы остаются вfeature/flash-read-cache безstaging/commit;
plan-fat12.md не изменён и не добавлен в индекс. Classic не прошивалась.

Текущий progress: кеши занятости C9 снизили стоимость публикации изменённого
тома без изменения on-flash формата,количества erases вмодельном bulk и
контрактов атомарности. Общий production goal остаётся active: ещё есть
F401 Classic-v2 baseline ROM reserve deficit и другие пункты общей
квалификации,а значительные изменения всё ещё закрываются за22–33с.


## Release qualification: продолжение 10.10

Предыдущий turn дал evidence, меняющее действие: FMK preview и parser уже
внешние в F401 SETUP.APP; отдельный FMK.APP сам по себе не устраняет его
ROM deficit. На mini SETUP пока resident. Новый FMK.APP не добавлен.

В worktree перенесены изменения, сохраняющие таблицы и функциональность:

- GCC14 size build использует Oz, LTO partition=one, IPA PTA и отказ от
  inlining однократно вызванных функций. Native core hot paths остаются O3.
- 768 ROM commands занимают по3 bytes; constexpr constructor проверяет
  точное обратное преобразование каждого исходного слова. Недопустимое
  слово не может пройти constant initialization. ROM literals неизменны.
- UI metrics вынесены в словарь; glyph records содержат11-bit bitmap offset
  и6-bit metric index. Генератор проверяет bounds и полную M8 repertoire;
  bitmap pixels неизменны, два guard bytes защищают последний read.
- SETUP и MARKDOWN используют имеющиеся resident memory/string runtime
  services. Проверяются runtime pointer и каждый slot; новых ABI slots нет.
- Для f411-classic-v3-usb-screen выбран внешний SETUP: его resident source
  buffer иначе мешает APP+staging memory gate. Прежние бюджеты сохранены.
  ELF gate разрешает resident FMK decoder только при встроенном SETUP.

F401 Classic-v2: было260464/262144, свободно1680 при требовании4096.
После packing/flags257812, свободно4332; в следующей fresh matrix257804
(4340). Core ctor/stack/native gates PASS. SETUP loaded20448/20480,
container9158. MARKDOWN container14763 превысил14336; shared runtime снизил
его до13482, loaded16976. Budget не повышен.

Strict F411 matrix /private/tmp/mk61-c9-release-final-f411-matrix:
все16 variants PASS, exit0. O3 и stock-linker extra checks PASS.
Continuous Clang18 + AppleClang ASan/UBSan CI release-verified PASS, exit0,
включая все768 constexpr words, native/scalar traces, exact543 glyphs /
24845 pixels, storage/VFAT software and STM32 CRC, mutations/faults/wear.
Эти PASS предшествуют последующему сужению staging RAM-таблицы.

56EAC899 pinned mini F411/A00 installed:338716 bytes. Matched System
byte-readbacks PASS. Physical coherence: COW replace, rename, delete/recreate,
cancel,3 BASIC numeric runs, warm-reset readback иcleanup PASS. RAW1536:
cold~1400us, warm~44–53us. CRC valid, VFATcode0/staged0, CRASHnone,
IWDGreset0; послеcleanup толькоSystem. Логи release-verified-mini-*.
Большой654-file A1495B32 HIL остаётся отдельным ранее завершённым замером.

ARM qualification разделена без удаления старого корпуса: --setup-only
и--viewers-only используют те же callbacks и реальные resident helpers.
SETUP refusal при missing/incomplete shared runtime, settings, invalid/valid
FMK preview PASS наF401/F411, по3 addresses. Новый MARKDOWN, WBMP, CHIP8,
links/back, exact UI glyph frames для12/14/16 и family alias PASS наобоих
ELF и3 addresses. Исправлены fixture: native file_read возвращает M8,
а UTF8 преобразуется при host import;2-row character mode должен перелистнуть
heading/target page перед выбором ссылки. Modern compiler/VM/INPUT отдельный
ARM flow PASS. Старый общий language fixture падает доUI наlegacy RUN;
его результат не выдаётся за qualification нового compiler flow.

F401 matrix не завершена: capability A00 USB не хватило144 bytes для
APP20480+stage2560. В RAM g_stage_physical измененаu32→u16: экономия256 bytes.
Geometry capped128MiB =>32768 sector indices; static_assert сохраняет proof.
On-flash addresses иC9 format остаются32-bit и неизменны. Дополнительный
host shim режим128MiB (обычный16MiB) подтвердил write/remount/discard
наверхних sector indices дляsoftware/STM32 CRC иF411 сASan/UBSan, exit0.
Fresh exact-contract canary и заключительный stage-u16 CI выполняются.
Полные матрицы после этого последнего FS изменения ещё должны подтвердить
budgets;56EAC899 пока использует прежнюю32-bit transient table.

Незакрытый extra gate: F411 STOP ws0010 static71464 >32768. ELF показывает
resident VM image_cache24576, MSC transport8308 иworkspace8192 среди крупных
буферов. Этот gate не ослаблен; алгоритмы их lifetime/ownership ещё не менялись.
STOP-classic иArduino F401 extra checks не выполнены после остановки runner.
Общий production goal остаётсяactive. Hardware Windows/Linux иphysical power
cuts не проводились; software fault injection иwarm resets не подменяют их.
Все изменения unstaged/uncommitted;plan-fat12.md не менялся. Classic не прошита.

Exact-contract stage-u16 F401 A00 USB canary завершён PASS,exit0:
free23152, USBDISK20476 иstage2560 одновременно; ctor иearlyDFU PASS.
Полные новые stage-u16-final F401/F411 matrices иCI выполняются.
Логи /private/tmp/mk61-c9-stage-u16-final-*; no PASS доих завершения.


## Последний staging вариант: подтверждения 10.10

Предыдущий turn — progress: тип RAM stage indices сужен без изменения wire,
128MiB fault-safe mock проверен, F401 canary восстановил APP+stage coexistence.
В этом turn authoritative результаты stage-u16-final: continuous Clang18 +
AppleClang ASan/UBSan CI exit0; F4019 cases exit0; F41116 cases exit0.
Cross-MCU WS RAM comparison отдельноPASS: F401 delta−24<=0, F411+156<=256,
F401USB−24<=0, F401graphics+0<=16. Логи stage-u16-final-*.

Штатный F411/A00 8D200E94 установлен наpinned mini,338716bytes; CRC valid.
Matched System byte-readback PASS. Physical coherence9 checks PASS: COW,
rename, delete/recreate, cancel,3 BASIC numeric runs, warm reset/readback,
cleanup. RAW1536 cold~1400us, warm~52–54us. Native fixtures убраны.
Normal macOS USB transaction PASS: Cyrillic LFN file85UTF8→59M8 bytes,
C6 readback2/2, import/export, eject2, CDC2, reset1, cleanup1.
VFATcode0/staged0/borrow0, CRASHnone; аппаратно64KiB F401 не проверяется.

Остались два известных дополнительных gates. Stock F401 Arduino/UC1609:
sealed260884,free1260<2048. Prototype compile size flags даютfree1584;
сlink flags1516, всё ещёнеPASS. Inline-threshold prototype измеряется;
real Arduino policy не менялась. Основная direct-GCC matrix9/9 проходит.

Изолированный /private/tmp/mk61-c9-ram-lifetime-prototype проверяет lazy
stable heap allocation WORKSPACE/BULK, VM cache иMSC handle. MSC память
готовится вforeground доSET_CONFIGURATION; IRQ не выделяетheap. Cache24KiB
иtransport8192 сохранены. Это ещёнеproduction implementation ивworktree
неперенесено;device его не получает.
Private STOP ws0010 globals30140<=32768, classic40272<=49152; обесборки
ctor/ROM/DFU/RTC/STOP gatesPASS,exit0. ПредварительныйAPP check тампоказывает
толькоinitial free:84280/74152 иещёнеучитываетпоследующееlazy allocation.
Не выдавать его отдельно заruntime memory qualification.

Real ARM newlib nano allocator prototype исполненвUnicorn для3/4 буферов,
непересечение исохранностьpattern проверены: requested41076/49268,
heap_growth41100/49300; послевсехвыделений остаётся43168/24832,
тоестьAPP20480+stage2560 ещёпомещаются. Лог prototype-heap-arm,exit0.
Нужно закрыть lifetime/failure/IRQ иallocator gates/диагностику передadoption,
учестьfuture lazy heap вELF memory gate ииспытатьresident/APP flow/device.
Текущаяstable worktree по-прежнемуимеетstatic71464 STOP RAM failure;
еёлимитнеослаблен. Общийproduction goal active;всёunstaged/uncommitted.

Arduino inline-threshold100 prototype terminalFAIL: FLASH overflow372 bytes.
Этотпуть не принят; действующаяworktree size policy не менялась этим опытом.
Послеcurrent mini USB HIL устройство вернулосьвCDC, fixtures cleanupPASS.


## Retained foreground buffers: adopted 10.10

Предыдущийturn — progress: реальныйARM lifecycle подтвердилIRQ refusal,
workspace retention/partition, APP+fullstage coexistence, OOM immutability.
В этомturnimplementation перенесена вworktree: F411 WORKSPACE/BULK,
VM image cache иMSC handle выделяются при первом foreground использовании
и сохраняют адрес/данные доreset. Объёмы8192/8192/24576/8308 неизменны.
F401 остаётсяstatic. Allocation запрещена вIRQ иeviction transition;
приOOM можно освободитьтолькоreclaimable idle OVERLAY, затемодинretry.
USB prepare создаётBOT handle доenumeration; SET_CONFIGURATION неallocates.

ELF absolute reserves учитывают всеfuture retained allocations +32 bytes
perblock. APP gate теперь проверяет effective free послеэтихрезервов:
WS43104,Classic24736>=20480+2560. Не выдаватьinitial free84/74KiB за
доступную память одновременно со всеми буферами. StaticSTOPRAM30140/40272
укладывается впрежние32768/49152. Обаreal STOP gatesPASS,exit0.

Fresh retained-final F411 matrix16/16PASS; continuous Clang18+AppleClang
ASan/UBSan CIexit0, storage/USB/faults/wear безизмененияформатаC9.
ARM lifetime наfresh WS/Classic ELF PASS; SETUP/preview иWBMP/Markdown/
CHIP8/точныеUI glyph frames PASS наClassic/A00 по3addresses. Modern
compiler/VM/INPUT flowPASS. Fixture теперь получаетworkspace черезреальную
Lease и размещаетinput/APP послеfuture heap reserve: староеplacement
перезаписывалоmalloc header и8KiBworkspace; этиfailed trials неproduction bug.
НовыхFS compatibility readers илиmigration нет. Всеизмененияunstaged.

Pinnned mini D917095A F411/A00 установлен:339036bytes,CRCvalid.
Systembyte-readbackPASS. Physical9-check coherencePASS: COW,rename,
delete/recreate,cancel,3 BASIC numeric runs,warmreset/readback,cleanup.
RAW1536 cold~1400us,warm~52us. OOM/heapIRQ ARM checked separately;
невыдаватьhost models заphysical power cuts. Normal macOS USB85UTF8→59M8
CyrillicLFN PASS:readback2/2,eject2,CDC2,reset1,cleanup1,VFATcode0/staged0,
CRASHnone,IWDGreset0. Full654-file HIL выполняется:host320creation иdelete/
refill107;логretained-final-mini-full-hil,handle27379. Доterminalexit неPASS.

Arduino F401 ROM остаётсянезакрыт: noinline setupfree1296<2048;
inline-constexprM8 tablesfree1272<2048; localcoldSETUPservice1272<2048.
Неудачныйoutline-services wrapper не изменилdispatchиз-заassert наwrongfile,
поэтомуегоразмерневыдаётсязаэффектoutlining. Этиprivate candidates неadopted.
Current direct-GCC F4019/9 остаётсяраньшепроверенным; RAMchangeF411-specific.
Дляcomplete нужныROMgateArduino,окончательныйhardware workload/audit и
проверкаproduction sourcediffs. UNMAPdisabled. Classicпока не прошита.

Retained-final full mini HIL terminalPASS,exit0:320 native empty+320host,
1980readbacks/146456bytes,1interruptedfsput,5warmresets,delete/refill107,
cleanuptrue. Total627.38s,maxnativecommand19.623s,CRASHnone,VFATcode0/staged0,
IWDGreset0. HIL log retained-final-mini-full-hil. Устройство вернулосьвCDC,
послеfixtures толькоSystem. Это подтверждает current adopted heap buffers
вбольшомC9 workload; Classichardware всё ещёнеперепрошиваетсявэтойфазе.

Текущийprogress: RAM issue закрыт кодом,неизменённымиSTOP budgets иfuture
heap accounting. CI,16F411,ARM lifecycle/settings/viewers/compilerflow,
physicalcoherence/USB/fullworkloadPASS. ArduinoF401 ROM ещёнеPASS; последний
coldSETUPprototype сохраняетfree1272<2048. Онвworktreeнеперенесён.
Общийproductiongoalactive;workingindexempty,plan-fat12untracked/uncommitted.

## Classic staging pressure: исправление после failure

BBCF81B2 с шестью matched System и 30 Games отказала после 232 host writes:
staged273 + dirty31, E1231 CACHE, borrow0x4000A. ESC вернул CDC; crash none,
watchdog reset0. Все Games35480 bytes verified после failure. Firmware не
перепрошивалась вслепую, failed subtree сохранён.

Точный host baseline принимает301 staged records, поэтому одного raw
journal недостаточно для целого сеанса. Catalog relocation probe не дал
добавочной ёмкости и не принят. Mounted checkpoint replay обнаружил потерю
принятых данных до появления FAT/dirent: sync удалял unclaimed sectors.

В worktree sync теперь сохраняет unknown sectors при mounted import; final
close по-прежнему их освобождает. Добавлен regression data->sync->metadata
на512KiB/16MiB, полный VFAT ASan/UBSan corpus PASS. Два retirement callback
объединены в один mask lookup; F401 canary USBDISK20444/20480, resident257532,
free4612>=4096. Descriptor/ABI/FS format не менялись.

Resident USB foreground на512KiB делает промежуточный mounted sync под
pressure; IRQ только проверяет RAM и откладывает пакет. Read-only rejection
не отвергает следующий host packet, чтобы ОС могла закончить транзакцию.
Host replay с31cache slots иреальными System/Games:5 checkpoints,320 payload
readbacks PASS. Firmware hardware сэтим исправлением ещёнепроверена.
Строгий CI,ArduinoF401 и16F411 выполняются; no PASS досвоего exit0.

### Окончательный кандидат checkpoint

Classic вышла после ESC, CDC восстановлен. Failed fixture удалена через
обычный C9 API; staged0, Games30/35480 bytes verified. Диагностика E1231
от предыдущего отказа сохранена. На mini 8DA01AC8: VFAT0/staged0, CRASHnone.

Mounted-sync regression и replay с начальным порогом64, 31 cache slots
пройдены под ASan/UBSan: пять checkpoints,320 payload readbacks.
PVD проверяется до checkpoint и вновь в общем обработчике BOT перед
записью. Shutdown использует тот же обработчик; IRQ не вызывает SPI/APP.
Arduino F401 candidate-v8 PASS: sealed260084,free2060>=2048,static35356,
stack1560<=5120. Дополнительные варианты v4-v7 не прошли ROM gate и
не прошивались на устройства. Резервы ROM/RAM и объёмы APP не уменьшались.

Exact-source qualification запущена: все9 F401, все16 F411, отдельный
контрактный Classic image для аппаратного повтора. До terminal exit и
полного hardware readback эти проверки не считаются PASS.

## Итог проверки окончательного исходного кода

Все основные9 F401 и16 F411 вариантов, Arduino F401, STOP2, O3, stock
linker2, cross-MCU RAM4, ARM lifecycle2 и System3-address проверки имеют
terminal exit0. Strict Clang18 + ASan/UBSan CI exit0. Hardware mini A00
9A9A8F37 и Classic UC1609 0ACCCFB9 завершили полный workload и очистку.
Classic Games30/35480 bytes совпадают после полного повтора чтения.

Classic single-candidate image и общий matrix image FB1630B1 имеют
разные CRC/размеры при одинаковых исходниках и compiler defines; код
содержит compile-time date/time. Оба source snapshot побайтно совпадают
с worktree, все шесть
System payloads идентичны. На плате тестировался именно0ACCCFB9.

План P0–P4 подтверждён предыдущими layout/density/fault/GC отчётами и
окончательными сборками/аппаратными проверками этой фазы. P5 остаётся
решением не реализовывать UNMAP: измеренного выигрыша нет, удаление
и повторное заполнение работают через FAT import + GC. Legacy FS readers
и migrations отсутствуют; fallback volume serial не читает старые форматы.

Основной plan-fat12.md:69137 bytes,mtime1791571330.3171322,без изменений.
Коммит изменений выполнен в `feature/flash-read-cache` 11.10.2026; перенос
в main в этот запрос не входит. Все временные hardware fixtures удалены,
обе платы вернулись в CDC.
