# Порционные M8 преобразования и кеш USB-текстов

База: d0cce726f. Ветка разработки: feature/m8-usb-stream.
Формат C9, APP ABI, узлы и границы FAT не изменяются.

Новый builtin F411 экспорт проверяет полный CRC/ZX0 payload перед
публикацией decoded cache. Во время MSC pinned staging остаётся в OVERLAY;
cache использует только свободную APP-арену и уступает её реальному APP.
Курсор из двух u32 хранится в восьмибайтном заголовке lease. Обратное
чтение пересчитывает позицию по проверенной RAM-копии. Нехватка RAM,
чужой APP и большие файлы используют прежний полный проверяемый stream.

UTF8 импорт идёт порциями до64 bytes с сохранением границы символа.
Четыре ASCII или обычные русские символа обрабатываются word-кернелем;
неудачный probe отключает повторные probes на восемь scalar characters.
Для коротких LFN используется word prefix и scalar suffix. Неправильный
UTF8, unsupported Unicode, controls и capacity ошибки проверяются до APPLY.
Четырёхбайтный UTF8 всегда отвергается: M8 содержит только BMP codepoints.
SIMD32 intrinsics не добавлены. F401/external USBDISK сохраняют компактный
скалярный путь, исходные APP/Flash/RAM резервы не ослабляются.

## Реальные USB-замеры первого кандидата

macOS, F_NOCACHE requested, обычные файлы,512-byte reads,5 повторов.
Каждый текст содержит3584 M8 bytes; экспортное UTF8 содержимое и импортные
копии проверены побайтно. Это end-to-end измерения, не SRAM микробенчмарк.

| Плата | Текст | Baseline read median,ms | Candidate read median,ms | Ускорение |
| --- | --- | ---: | ---: | ---: |
| mini | ascii | 442.300 | 31.699 | 13.95 |
| mini | russian | 1792.096 | 125.899 | 14.23 |
| mini | alternating | 1096.380 | 121.046 | 9.06 |
| mini | program | 905.500 | 95.826 | 9.45 |
| classic | ascii | 447.276 | 33.562 | 13.33 |
| classic | russian | 1824.388 | 144.475 | 12.63 |
| classic | alternating | 1109.102 | 121.377 | 9.14 |
| classic | program | 877.382 | 95.922 | 9.15 |

Write/fsync измерен по одному образцу; выраженного стабильного ускорения
нет. Eject: mini6307→5702ms, Classic4505→4228ms, четыре host копии.
Долгий выход после640 маленьких объектов требует отдельных измерений.

Первый кандидат mini EBD72B7E: full320 empty+320 host HIL PASS,
1980 readbacks/146456bytes,5 resets,delete/refill107,cleanup=true,
631.72s,max native19.309s,VFAT0/staged0,CRASHnone,IWDGreset0.
Classic6402CF5C: текстовый USB benchmark и COW/rename/delete/cancel/BASIC
coherence PASS. Это промежуточные подтверждения, не final-source hardware.

## Окончательная версия

v9 устраняет дублирование verified cache loader и лишние narrowing/guards.
STOP2 PASS: static RAM WS30140,Classic40272; effective future heap
43104/24736, APP20480+stage2560 помещаются. Classic sealed393204,
free131084>=131072. Предыдущие v1-v8 STOP ROM candidates не прошли gate;
резервы не уменьшались. Наименьшая положительная ROM margin проверяется
по каждому фактически собранному artifact.

Pinned normal final images: mini B1AA6D73,340460bytes; Classic7B7D50A3,
393212bytes. Их hardware повтор,16F411 release и exact v9 CI прошли.
F4019/9 и ArduinoF401 PASS; read-cache disabled code не менялся.
Exact-source STOP/ARM lifetime passed. Кодек: all BMP units in every lane,
all UTF8 byte pairs,partial outputs/capacities и protected input/output ends
прошли под ASan/UBSan. Decoded cache: pin stage + cache in APP,random/backward
UTF8 byte ranges,one ZX0 decode,real APP eviction and unchanged APP bytes PASS.

PDF storage description обновлён; окончательная visual QA и hardware audit
прошли. plan-fat12.md не изменён.

## Final v9 текстовые операции

| Плата | Текст | Baseline median,ms | Final v9 median,ms | Ускорение |
| --- | --- | ---: | ---: | ---: |
| mini | ascii | 442.300 | 31.647 | 13.98 |
| mini | russian | 1792.096 | 125.829 | 14.24 |
| mini | alternating | 1096.380 | 119.837 | 9.15 |
| mini | program | 905.500 | 94.389 | 9.59 |

mini: baseline build 9A9A8F37, final B1AA6D73; eject 6307→6014ms. Все payloads и импортные копии совпали.

| classic | ascii | 447.276 | 32.129 | 13.92 |
| classic | russian | 1824.388 | 139.190 | 13.11 |
| classic | alternating | 1109.102 | 120.693 | 9.19 |
| classic | program | 877.382 | 95.202 | 9.22 |

classic: baseline build 2E9648F8, final 7B7D50A3; eject 4505→4362ms. Все payloads и импортные копии совпали.

Окончательные16 F411, STOP2,O3,stockF401/F411 и cross-RAM4 имеютexit0.
ARM lifetime2,SETUP/viewers2ELF×3addresses,compiler/VM/INPUT3addressesPASS.
Final mini B1AA6D73 full320+320HIL PASS,1980readbacks/146456bytes,
5resets,cleanuptrue,634.86s,maxnative19.684s. Classic final полный HIL и exact v9 Clang18/ASan/UBSan CI завершились
с terminal exit0. Предыдущие прогоны хранятся отдельно.
PDF:15pages,contact-sheet и новые pages6/12 визуально проверены.

## Завершение v9

Окончательные mini B1AA6D73 и Classic7B7D50A3: full320 native empty+320host
файлов,1980readbacks/146456bytes на каждой,прерванный fsput,5warmreset,
delete/refill107,cleanuptrue. Mini634.86s/maxnative19.684s;Classic372.37s/
maxnative8.767s. Eject mini37.572/25.270s,Classic9.337/8.301s. Это workload
640маленьких объектов; ускорение текстового чтения не ускорило большой
изменённый том mini. Write/fsync в четырёх текстовых образцах существенно
не улучшился; не выдаётся за гарантированное ускорение записи.

GamesClassic30/35480bytes совпали до и после всех проверок. На обеих
платах финальноCDC,firmwareCRCvalid,VFAT0/staged0,CRASHnone,IWDGreset0.
Все тестовые ветки удалены. Exact v9 CI exit0:Clang18+ASan/UBSan,CRC/
fault/torn-write corpus,UTF8/BMP/protected-end tests. All16F411,9F401,
ArduinoF401,STOP2,O3,stock2,cross-RAM4 иARM/System gatesPASS. F401 compiled
scalar code не менялся при v2-v9 cache-only edits;RAM/ROM reserves retained.

Все 367 файлов code/SDK совпадают с зафиксированным для проверок
манифестом исходников. plan-fat12.md: 69137bytes, mtime1791571330.3171322,
без изменений. Итог включает код, benchmark runner, регрессии,
документацию/PDF и этот отчёт.
