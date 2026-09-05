# Release, диагностика и передача ввода

## Один контракт сборки

`tools/release-contract.json` задаёт зависимости, профили, capability cases и
бюджеты. `tools/release_contract.py` валидирует данные и отдаёт выбранные cases
Bash/PowerShell-сборщикам; GitHub Actions вызывает те же entry points.
`tests/run_release_preflight.sh` — полный локальный проход. Отдельно
`tests/run_ci_strict.sh` проверяет host-код тем же Clang 18, что CI, и ASan/UBSan.

Каждый firmware case создаёт `resource-report.json` и `.md`: sealed BIN,
Flash/headroom, секции ELF, static RAM, максимальный статический frame и
крупнейшие символы. Суммарный отчёт формируется `aggregate-reports`.
Это воспроизводимый ресурсный контракт, не обещание побитово одинаковых BIN
на разных host OS. Лабораторный F401 case с USB Screen и графикой WS0010 имеет
отдельный 512-байтный Flash gate; продуктовый F401 — минимум 8192 байта.

## VFAT: причина ошибки — значение, не строка

`virtual_fat::Diagnostic` — 28 байт: `code`, `phase`, `flags`, два `u32` context
и 16-байтный безопасный UTF-8 prefix имени. Состояние вместе с first-cause latch
занимает не более 32 байт и заменяет прежние указатель и текстовый буфер.
В пределах одной попытки глубокая причина не перезаписывается общим отказом
внешнего уровня. Очистка при откате может добавить `RETRYABLE`, сохранив причину.

Обычный выход из USB-диска и пустая синхронизация не стирают последний отчёт;
его заменяют следующая ошибка, успешный реальный импорт или `vlog clear`.
Никакого дополнительного журнала во Flash нет. Машинная строка `VFAT v=1`
не зависит от локали; номера публичны и не переиспользуются. Экран показывает
`USB E12xx`, словарь объяснений находится на компьютере, в
`tools/vfat_diagnostic.py`. Формат и пример расшифровки — в `tools/README.md`.

## Один владелец передачи клавиши

`keyboard_core::Event` — проверенное представление прежнего байта события,
не новый wire format. В `DeliveryQueue` по-прежнему ровно восемь мест FIFO;
ещё пять байт отмечают клавиши, чей текущий жест уже использован при переходе.
Счётчик переполнений насыщается, виден как `KBD overflow=N` в `prof` и считает
отказы принять валидное событие (включая повторяемый USB backpressure).

Потребитель получает событие через `kbd::poll_event()`. Когда PRESS вызвал
переход, он вызывает `kbd::handoff(event)`. Уже стоящие в очереди и будущие
RELEASE/repeat **этого жеста** поглощаются, соседние клавиши сохраняют порядок.
RELEASE заканчивает жест, поэтому следующее отдельное нажатие той же клавиши
работает. Терминальный `kbd` — законченный PRESS-пульс без удержания; ожидать
несуществующий RELEASE от него нельзя.

`get_key_wait()` и локальные wait-helper, документированные как принимающие
клавишу перехода, уже выполняют handoff; вызывать его повторно для одного
жеста не требуется. Низкоуровневое чтение само по себе handoff не делает.
Меню, viewers, VM, splash и resident APP adapter используют этот контракт;
`exclude_before`, глобальный drain при выходе из меню и повторный reset
debouncer удалены. Формат APP и публичная таблица loadable API не меняются.
Приватные System APP symbols пересобираются вместе с resident, к CRC которого
они и раньше были привязаны.

USB Screen хранит requested и delivered состояния отдельно. `deliverFront`
меняет held-state только после принятия события общей очередью. Даже если
PRESS и RELEASE получены за один USB service pass, экран, открываемый PRESS,
видит удержание до доставки RELEASE. Abort отбрасывает недоставленные нажатия
и доставляет отпускания уже принятых — тем же путём, без отдельного раннего
сброса held-state. Физический сканер не снимает подавление удерживаемой
USB-клавиши только потому, что соответствующая физическая кнопка отпущена.

## Интерфейс терминала

`terminal.hpp` содержит объявления; тела методов и единственные определения
состояния — в `terminal.cpp`. Каталог команд строится из
`terminal_commands.inc`: один текстовый pool, четырёхбайтные entries и
128-байтный CRC-8 index. Hash никогда не заменяет полное сравнение имени,
одинаковые имена отвергаются compile-time даже при одинаковом command id.

`terminal_key_sequence.cpp` хранит только исключения и таблицу регистров;
регулярные группы opcodes вычисляются. Совместимость всех 256 входных байтов
на трёх раскладках проверяется против прежней таблицы из characterization
fixture. Имена, aliases и help проверяются против прежнего каталога с USB
Screen и без него (кроме намеренно обновлённого описания `vlog`). Перенос
обработчиков не вводит виртуальных методов, registry, heap или новых static
constructors. Interactive/script terminal используют одну реализацию, сохраняя
прежние различия адресации команд клавиатуре и непосредственно ядру.

## Ограниченные host-проверки

| Проверка | Production surface | Бюджет / инвариант |
|---|---|---|
| `run_keyboard_tests.sh` | Event, DeliveryQueue, debounce, wake, external keys | Все 1560 различных пар cause/neighbor; быстрые и длинные жесты, release/repress, overflow |
| `run_usb_screen_virtual_keys_tests.sh` | VirtualKeyQueue + DeliveryQueue + ExternalKeyState | Все 40 USB-клавиш, ранний RELEASE, backpressure и abort во время handoff |
| `run_terminal_tests.sh` | Каталог и parser/editor/protocol | Старые имена/help, aliases, полное сравнение при hash collision |
| `run_keyboard_layout_profile_tests.sh` | Компактный opcode mapping | Все 256 значений на mini/classic/40th |
| `run_ui_contract_tests.sh` | Реальные composition/layout bodies и pure display helpers | Compact/extended font setup, 4 строки, EN/RU, порядок drop→profile→refresh→save, часы, splash state, USB error, Markdown boundary, mixed WS0010 |
| `run_parser_hardening_tests.sh` | APP header/Reader/payload и ZX0 decoder/range decoder | Seed `0x4d4b3631`; APP 15904, ZX0 5828 проверок; canaries и output/read bounds |
| `run_virtual_fat_tests.sh` | VFAT importer и настоящий C5 в host harness | 587 мутаций FAT/dirent/LFN; исходный файл сохраняется при отказе, включая end/reboot/reinit; default/F401 |

R5 извлекает выбранные тела production-функций перед компиляцией, с `#line`
на исходник. Recording surface хранит операции и текст; копии renderer или
menu-алгоритма в fixtures нет. Изменение/удаление выбранного symbol останавливает
тест, а не использует старую копию. Эти тесты не доказывают работу SPI или
пикселей физического дисплея — transport проверяется отдельно.

R6 — детерминированный bounded hardening, а не заявление «всё fuzzed».
APP в этом проекте не содержит runtime relocation/import table: native symbols
связываются при сборке и проверяются resident CRC. Harness проверяет фактический
формат и payload, **не исполняет произвольный native-код** и не эмулирует MPU.
VFAT harness использует свой существующий adapter проверки APP, а не настоящий
ARM loader. Повреждённые файлы не подаются в живую файловую систему устройства.
Truncation, bit mutations, предельные длины и integer-wrap candidates проходят
ASan/UBSan; обнаруженный crash должен стать отдельным коротким regression test.

Для изменений handoff достаточно короткого физического сценария на доступных
раскладках: один ESC открывает меню, отпускание не закрывает его; второй
отдельный ESC возвращает калькулятор, следующая цифровая клавиша срабатывает
один раз. Host-данные не подменяют измерение физической latency, и длительные
испытания STOP/питания не повторяются без изменения их реализации.
