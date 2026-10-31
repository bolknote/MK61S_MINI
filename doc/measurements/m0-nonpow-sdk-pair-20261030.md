# Pico H nonpow: полная SDK-пара, 30 октября 2026

Исторический отчёт отдельного этапа. Итог физических замеров и возврата
устройства: [nonpow 31 октября](m0-nonpow-20261031.md).

Проверены две полные сборки Pico SDK2.2.0: immutable `main`
`eaaff37349149f86ebe7c25275a09da3f6ae906d` и тот же снимок с ровно12
математическими изменениями из HOST-пакета.653 tracked файла извлечены
непосредственно из Git;69 математических файлов базы побайтно совпали с
квалифицированным origin. В кандидате656 файлов, включая3 новых include.
Изменения Runner/UI из main сохранены, посторонний WIP не импортирован.
Запрещённый research/fermat-search не читался и не копировался.

## Сборка и ресурсные пределы

| Показатель | База | Кандидат |
|---|---:|---:|
| GNU text | 1161954 | 1162178 |
| BIN / занято Flash | 1537008 | 1537056 |
| Статическая main RAM, по `__end__` | 126284 | 126284 |
| GNU data+BSS (другая классификация SRAM-кода) | 83364 | 83364 |
| Hot SRAM / предел | 4096 /4096 | 4096 /4096 |
| Core0 stack reserve | 32768 | 32768 |
| `.rodata` | 278844 | 278844 |
| CRC32 sealed image | A05E7CAC | 78475A12 |

Итог: код+224 байта, BIN+48 байт, новых таблиц0, статическая RAM+0.
Все множества и размеры STT_OBJECT пяти математических единиц совпали;
изменилось содержимое только существующей4096-байтной `log_near_table`.
Отдельные секции: `.text`+1096, math extension+72, trig core−992, exp core+48.
Фиксированное размещение делает увеличение BIN отличным от роста GNU text.
Flash не пересекает последние8192 байта settings journal. Main RAM остаётся
в224КиБ; hot не пересекает32768-байтный стек core0, LCD DMA — стек core1.

## Что проверено

Обе сборки и все проверки завершились с exit0, повторных SDK-сборок0.
По164 compile units: после нормализации путей source/build и единственного
build-ID define флаги совпали точно. Для C/C++ задано `-ffp-contract=off
-fno-fast-math`; runtime и CORE-MATH — `-Os -fno-lto`. ARMv6-M, soft ABI,
default owned M0 provider, прежние linker/CMake/SDK source без изменений.
Код из libgcc archive не извлечён, undefined symbols0. Неиспользуемый sqrtf
может быть удалён штатным GC; наличие owned input section сохранено в map.

Из3356 ранее frozen SDK-файлов, toolchain14.2.1 и pioasm2.2.0 inputs повторно
проверены хэши. Готовый pioasm из предыдущих двух успешных SDK-сборок совпал
побайтно, скопирован в частный cache. Fetch/install/новая сборка hosttool0.
SDK tracked state чист до и после. По742/745 реальных compiler imports
разница — только12 разрешённых math paths (3 новых); неизменные SDK/toolchain
inputs совпали. Два generated текста содержат разные пути role; их raw-хэши
сохранены, canonical bytes после замены только префиксов совпали. Boot2 bytes
совпали точно. CMake imports и полный Ninja command graph сохранены отдельно.

Sealed ELF↔BIN↔UF2, canonical CRC, footer placement и UF2 family/address
проверены. Патч footer не меняет program/section headers и RAM initializer
LMAs. Старый регрессионный seal-тест и UF2-тест прошли. Бинарные области
сложения/вычитания совпали с независимо проверенными standalone ELF каждой
версии. Map и ограничения всех фиксированных math slots проверены.

В immutable baseline есть11 предупреждений:5 misleading-indentation в
native_display,3 format-truncation в services/service_runtime,3 linker
diagnostics (FLASH declaration/redeclaration и GNU-stack у crtn.o).
Кандидат сохранил тот же нормализованный список; новых math/compiler warnings0.
Это сохранение диагностик базы, а не их исправление. Неудачный первый checker,
ожидавший только2 предупреждения, и исправления нормализации generated paths
сохранены; исходники и SDK не пересобирались из-за этих проверок.

## Отдельные вердикты

SDKREADY означает успешную полную сборку, целостность и layout/footprint.
Нового ARM-исполнения и физических замеров в этом SDK-этапе нет.
Предыдущие HOST-данные сохранены:170 известных проигрышей корректному Qfplib
устранены; при этом1879 входов медленнее нашей прежней базы. Все raw ADVERSE
карты и средние по общему корректному подмножеству остаются в HOST-отчёте.
SDKREADY не подменяет конечные HOST-тесты машинным доказательством и не
подменяет число инструкций измерением циклов на Pico H.

M4 product/source вне12 RP-ограниченных изменений не затронут; ранее5
disabled-target контролей сохранили код/символы/релокации. Новая полная M4
прошивка этим не объявляется. Pow-разработка отложена; SDK-этап не выполнял
ARM/pow/device вызовов.

## Артефакты

Корень: `.build/m0-nonpow-sdk-20261029-001/` (создан до смены даты).
`SOURCE-PREPARED.json`, `PLAN.json`, `LEDGER.json`, `SDK-PAIR-RESULT.json`,
обе полные map/compile databases, import graphs, math object sizes, source
snapshots, build/output files и исправления операторов сохранены.

| Артефакт | SHA256 |
|---|---|
| Base BIN | `57759fb18d358e799b943253b89c7091f181e6d69c6003dc42c9b264680754c9` |
| Next BIN | `736b1dca8556e3015f7532e86f7f2d57cb3a207548e03145c23ab27ed8111c81` |

Устройства, primary checkout и SDK source не изменялись. Следующий этап —
отдельно связанный HIL-план с точным caller, резервными копиями и возвратным
resident; аппаратные операции требуют отдельного RootGo.
