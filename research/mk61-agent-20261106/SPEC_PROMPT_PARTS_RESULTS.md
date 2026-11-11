# Отдельные сокращения трёх разделов промпта

На development выбран формат **original**; для второй панели заранее зафиксирован вариант **notes**. С BU1500 на прежних 256 задачах завершения 276→282 из 512, исправления 110→103 из 256 (прежний → новый). Рабочий профиль не заменён.

Дообучения не было: исполнитель Q4 и переводчик BU1500 неизменны. Три варианта меняют по одному разделу прежнего запроса: список вызовов, объяснение DIAG, повторяемые общие правила. Остальные два раздела сохраняются дословно. Сокращения в точности взяты из предыдущего неудачного совместного варианта; новые формулировки здесь не подбирались.

Экономия токенов на одинаковом состоянии: вызовы — 15, DIAG — 43, общие правила — 68. На 5823 сохранённых запросах (3240 уникальных) подтверждено сохранение всех публичных переменных полей, углового режима и остатка действий. Все три сокращения вместе точно восстанавливают прежний BZ-вариант с экономией 126 токенов.

Во всех полных циклах сохранены условие, константы, стартовый код, открытые входы, эмулятор, RUN, проверка DONE, откат, 12 действий и контекст 1024 с FP32 KV. Начальные SPEC и все их токены совпали с прежними ответами. gold подставляет эталон при первом и повторном разборе и не является самостоятельным решением; own использует обычный BU1500 без эталона. Первые запросы каждого эпизода дополнительно проверены: они отличаются от прежних только выбранным сокращением, ещё до расхождения действий.

Использованы уже изученные development128 и closed256: это диагностические панели, не новый закрытый экзамен. Каждый из трёх вариантов проверен на development в обоих режимах. Выбор заморожен до второй панели: минимум +2 правильных завершения в обоих режимах, не меньше исправлений и доведённых правильных стартов, не больше принятых ложных DONE и итоговой порчи. Из прошедших вариантов предпочтение по own-завершениям, own-исправлениям, gold-завершениям, gold-исправлениям, безопасности, затем экономии токенов. Если никто не прошёл, сохраняется original; лучший новый вариант проверяется только для диагностики.

## Полные циклы

| Панель | SPEC | Сокращённый раздел | Завершено | Верный старт доведён | Ошибочный исправлен | Принятые ложные DONE | Итоговая порча | Переполнение | До первого действия |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| development | gold | Прежний | 152/256 | 97 | 55 | 0 | 0 | 70 | 33 |
| development | gold | Справка вызовов | 142/256 | 88 | 54 | 0 | 0 | 62 | 20 |
| development | gold | Справка DIAG | 155/256 | 100 | 55 | 0 | 0 | 46 | 2 |
| development | gold | Общие правила | 168/256 | 110 | 58 | 0 | 0 | 34 | 0 |
| development | gold | Все три вместе | 145/256 | 110 | 35 | 0 | 0 | 21 | 0 |
| development | own | Прежний | 136/256 | 86 | 50 | 3 | 1 | 73 | 32 |
| development | own | Справка вызовов | 125/256 | 78 | 47 | 1 | 1 | 72 | 22 |
| development | own | Справка DIAG | 135/256 | 88 | 47 | 4 | 2 | 48 | 1 |
| development | own | Общие правила | 148/256 | 96 | 52 | 5 | 2 | 36 | 0 |
| development | own | Все три вместе | 126/256 | 93 | 33 | 1 | 0 | 19 | 0 |
| closed | gold | Прежний | 299/512 | 180 | 119 | 0 | 0 | 137 | 55 |
| closed | gold | Общие правила | 315/512 | 204 | 111 | 0 | 0 | 61 | 0 |
| closed | own | Прежний | 276/512 | 166 | 110 | 13 | 5 | 142 | 54 |
| closed | own | Общие правила | 282/512 | 179 | 103 | 17 | 7 | 61 | 0 |

Итоговая порча измерена после отката неподтверждённого кандидата; неверные предложения WRITE считаются отдельно. Принятый ложный DONE отличается от ложного заявления, которое отклонила проверка.

| Панель | SPEC | Раздел | Неверный WRITE при верном старте | Ложных заявлений DONE / всех DONE | Повторных разборов |
|---|---|---|---:|---:|---:|
| development | gold | Прежний | 12 | 260/412 | 59 |
| development | gold | Справка вызовов | 20 | 277/419 | 183 |
| development | gold | Справка DIAG | 22 | 447/602 | 56 |
| development | gold | Общие правила | 19 | 466/634 | 67 |
| development | gold | Все три вместе | 18 | 786/931 | 171 |
| development | own | Прежний | 16 | 288/482 | 69 |
| development | own | Справка вызовов | 18 | 262/463 | 182 |
| development | own | Справка DIAG | 25 | 474/675 | 64 |
| development | own | Общие правила | 21 | 454/715 | 83 |
| development | own | Все три вместе | 17 | 826/1112 | 177 |
| closed | gold | Прежний | 47 | 505/804 | 156 |
| closed | gold | Общие правила | 55 | 1100/1415 | 155 |
| closed | own | Прежний | 48 | 504/827 | 164 |
| closed | own | Общие правила | 66 | 1072/1541 | 179 |

## Первый ответ на одинаковом состоянии

DIAG 04 — запрос пересмотра SPEC. В gold такая гипотеза уже правильна. Ошибки context_overflow/incomplete обозначают ошибку генерации, а не отдельную команду модели.

| Панель | SPEC | Раздел | Старт | Первый ответ |
|---|---|---|---|---|
| development | gold | Прежний | correct_start | ERROR:context_overflow=17, ERROR:incomplete=1, diag:04=25, done=48, write=37 |
| development | gold | Прежний | wrong_start | ERROR:context_overflow=16, ERROR:incomplete=2, diag:04=24, done=37, write=49 |
| development | gold | Справка вызовов | correct_start | ERROR:context_overflow=11, ERROR:incomplete=4, diag:04=87, done=9, write=17 |
| development | gold | Справка вызовов | wrong_start | ERROR:context_overflow=9, ERROR:incomplete=4, diag:04=91, done=6, write=18 |
| development | gold | Справка DIAG | correct_start | ERROR:incomplete=4, diag:04=23, done=57, write=44 |
| development | gold | Справка DIAG | wrong_start | ERROR:context_overflow=2, ERROR:incomplete=2, diag:04=21, done=50, write=53 |
| development | gold | Общие правила | correct_start | diag:04=29, done=61, write=38 |
| development | gold | Общие правила | wrong_start | diag:04=27, diag:07=1, done=58, write=42 |
| development | gold | Все три вместе | correct_start | diag:04=74, done=31, write=23 |
| development | gold | Все три вместе | wrong_start | diag:04=83, done=25, write=20 |
| development | own | Прежний | correct_start | ERROR:context_overflow=17, diag:04=26, done=48, write=37 |
| development | own | Прежний | wrong_start | ERROR:context_overflow=15, ERROR:incomplete=3, diag:04=25, done=40, write=45 |
| development | own | Справка вызовов | correct_start | ERROR:context_overflow=12, ERROR:incomplete=3, diag:04=86, done=9, write=18 |
| development | own | Справка вызовов | wrong_start | ERROR:context_overflow=10, ERROR:incomplete=3, diag:04=90, done=6, write=19 |
| development | own | Справка DIAG | correct_start | ERROR:incomplete=5, diag:04=25, done=58, write=40 |
| development | own | Справка DIAG | wrong_start | ERROR:context_overflow=1, ERROR:incomplete=5, diag:04=20, done=50, write=52 |
| development | own | Общие правила | correct_start | diag:04=31, done=62, write=35 |
| development | own | Общие правила | wrong_start | diag:04=28, diag:07=1, done=58, write=41 |
| development | own | Все три вместе | correct_start | diag:04=74, done=33, write=21 |
| development | own | Все три вместе | wrong_start | diag:04=83, done=25, write=20 |
| closed | gold | Прежний | correct_start | ERROR:context_overflow=27, ERROR:incomplete=2, diag:04=75, done=86, write=66 |
| closed | gold | Прежний | wrong_start | ERROR:context_overflow=28, ERROR:incomplete=1, diag:04=63, done=69, write=95 |
| closed | gold | Общие правила | correct_start | ERROR:incomplete=1, diag:04=63, done=110, write=82 |
| closed | gold | Общие правила | wrong_start | ERROR:incomplete=2, diag:04=58, done=111, write=85 |
| closed | own | Прежний | correct_start | ERROR:context_overflow=27, ERROR:incomplete=1, diag:04=74, done=86, write=68 |
| closed | own | Прежний | wrong_start | ERROR:context_overflow=27, ERROR:incomplete=1, diag:04=66, done=69, write=93 |
| closed | own | Общие правила | correct_start | ERROR:incomplete=1, diag:04=68, done=107, write=80 |
| closed | own | Общие правила | wrong_start | ERROR:incomplete=2, diag:04=70, done=104, write=80 |

## Парная неопределённость

Изменение относительно original, п.п.; 95% интервалы по 10 000 парных bootstrap-выборок задач, оба старта остаются вместе. Интервалы не учитывают выбор лучшего варианта на development и не превращают повторную панель в новый экзамен.

| Панель | SPEC | Раздел | Выиграно / потеряно эпизодов | Завершения [95%] | Исправления [95%] |
|---|---|---|---:|---:|---:|
| development | gold | Справка вызовов | 21 / 31 | -3.91 [-9.77; +1.95] | -0.78 [-9.38; +7.81] |
| development | gold | Справка DIAG | 26 / 23 | +1.17 [-4.69; +6.64] | +0.00 [-9.38; +8.59] |
| development | gold | Общие правила | 39 / 23 | +6.25 [+0.00; +12.89] | +2.34 [-7.05; +11.72] |
| development | gold | Все три вместе | 31 / 38 | -2.73 [-9.38; +3.91] | -15.62 [-25.00; -6.25] |
| development | own | Справка вызовов | 17 / 28 | -4.30 [-9.77; +1.56] | -2.34 [-10.16; +5.47] |
| development | own | Справка DIAG | 21 / 22 | -0.39 [-5.86; +4.69] | -2.34 [-10.94; +6.25] |
| development | own | Общие правила | 32 / 20 | +4.69 [-1.17; +10.55] | +1.56 [-7.03; +10.16] |
| development | own | Все три вместе | 22 / 32 | -3.91 [-9.77; +1.95] | -13.28 [-21.88; -5.47] |
| closed | gold | Общие правила | 54 / 38 | +3.12 [-0.78; +7.23] | -3.12 [-8.98; +2.73] |
| closed | own | Общие правила | 38 / 32 | +1.17 [-2.15; +4.69] | -2.73 [-7.81; +2.73] |

## Заранее заданный выбор


Справка вызовов: eligible=False, key=[125, 47, 142, 54, -1, -1, 15].

- gold_more_completions: False
- gold_wrong_starts_repaired: False
- gold_correct_starts_completed: False
- gold_false_DONE: True
- gold_correct_starts_corrupted: True
- own_more_completions: False
- own_wrong_starts_repaired: False
- own_correct_starts_completed: False
- own_false_DONE: True
- own_correct_starts_corrupted: True

Справка DIAG: eligible=False, key=[135, 47, 155, 55, -4, -2, 43].

- gold_more_completions: True
- gold_wrong_starts_repaired: True
- gold_correct_starts_completed: True
- gold_false_DONE: True
- gold_correct_starts_corrupted: True
- own_more_completions: False
- own_wrong_starts_repaired: False
- own_correct_starts_completed: True
- own_false_DONE: False
- own_correct_starts_corrupted: False

Общие правила: eligible=False, key=[148, 52, 168, 58, -5, -2, 68].

- gold_more_completions: True
- gold_wrong_starts_repaired: True
- gold_correct_starts_completed: True
- gold_false_DONE: True
- gold_correct_starts_corrupted: True
- own_more_completions: True
- own_wrong_starts_repaired: True
- own_correct_starts_completed: True
- own_false_DONE: False
- own_correct_starts_corrupted: False

Одиночные сокращения показывают эффект конкретного раздела при двух остальных прежних. Все попарные сочетания здесь не измерялись; взаимодействия частей нельзя объявлять установленными только по трём одиночным вариантам и прежнему совместному. Результат относится к этим числовым AST и старым весам, а не ко всем форматам и не к пределу ёмкости 3M.

## Следующий контролируемый обучающий опыт

Кандидат формата для адаптации исполнителя: notes, зафиксированный по development. Переводчик BU1500 и проверку оставить замороженными. Исполнителя начинать от прежних весов, обучать парным состояниям original/notes с одинаковыми проверенными целями и повтором прежних успешных исправлений. Это план следующего опыта; в текущем весов не обучали.

В курс включить: правильная SPEC + неправильный код → правильный WRITE; правильный код → недостающие RUN и DONE; неправильная SPEC при правильном/неправильном коде → DIAG 04 и повторный разбор без изменения программы; после исчерпания пересмотра неверной гипотезы → UNSURE. Исправления после DONE_REJECTED должны опираться на реальное численное контрпримерное состояние. Правильный код и подтверждённые результаты RUN не должны теряться при пересмотре условия. Цели WRITE и исходы циклов проверять компилятором и эмулятором.

Выбирать чекпойнт по полным циклам, сохранению прежних исправлений, ложным DONE и порче до/после отката, в обоих режимах SPEC. После выбора нужен новый заранее закрытый набор русских задач и Q4-проверка. Эти повторно изученные панели полезны для диагностики и регрессии, но не заменяют новый экзамен.

## Исполнение и артефакты

Все 52 проверенных реальных потоков исполнителя и переводчика совпали на B200, CPU и C++; представлены все три сокращения. Один буфер весов 2160856 байт, host-KV 5242880 байт, workspace 49152 байт. Физический PicoCalc не измерялся.

Обучающих обновлений 0. Все собственные GPU-задачи завершены, Qwen отвечает 200. Профиль приложения и устройства не заменён.

Артефакты: `.build/mk61-agent-20261106/spec-prompt-parts-v1`; `comparison.json`, `server-results/preselected.json`, `server-results/audit-roles.json`, `server-results/native-verification.json`.
