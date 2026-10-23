# dadd/dsub: subnormal входы и нули без C++ fallback

Прямой следующий остаток исходной CPU math цели. Отдельный private WIP
поверх low-normal кандидата; родитель и остальные review targets не менялись.

Сложение/вычитание теперь обрабатывает все классы входов своим assembly
кодом. Для E0/E1 используются точные целые коэффициенты в единицах2^-1074;
при необходимости54-битная сумма получает один tie-even round. Для normal
operand проверяется точная граница его rounding cell с учётом знаков,
power-of-two границы и чётности midpoint. Остальные случаи используют
прежние точные kernels с виртуальным exponent1 для subnormal coefficient.
Старый C++ fallback из этого блока удалён, новых fallback/trap нет.

Все18 оставшихся прежних subnormal-input проигрышей обойдены: среднее
**20.89 инструкции** против286.78 у родителя и64.78 у правильного Qfplib.
На3015 профилированных случаях новых проигрышей правильному Qfplib нет;
2623 быстрее родителя,392 равны,0 медленнее. Ошибочные raw ответы Qfplib
считаются отдельно в каждом текущем отчёте и не отбрасываются из данных.

70 261 целевой случай /210 783 ARM-вызова:0 ошибок у кандидата и родителя
против exact integer RNE и directed MPFR4.2.2. Проверены coefficient widths,
normal cell boundaries, parity ties, обе стороны smallest-normal и raw
sum2^53, обе роли аргументов, signed zero, Inf/NaN и целевой random.
NaN sign/payload policy также совпал с родителем побайтно.
Непрофилированные строки используются только для correctness, не speed claim.

Ещё1768 обычных/low/top/nonfinite контролей /5304 ARM-вызова совпали с
родителем по результату и числу инструкций. Это узкие unaffected controls,
а не повтор полной матрицы библиотеки.

Кандидат исполнялся как **отдельный ELF без прошивки или ROM**, с32-байтной
разрешённой областью записей стека. Наблюдаемая глубина20 байт на всех
вызовах. Проверяются R4–R11, восстановление SP, границы записей и сохранение
READY/DIRTY SIO. Для сравнения родитель использовал прежний ELF и captured
ROM; Qfplib исполнялась отдельно. Все цены здесь — инструкции, не такты.

Контрольные объекты: блок1204→1472 байта (**+268 байт**), новых таблиц,
literal words или global RAM нет. Весь публичный блок1472 байта равен
исполненному diagnostic body полностью, без исключаемых BL. Самостоятельный
object не имеет undefined symbols или relocations. Полный object убирает
зависимость от mk61_m0_dadd_slow; новых зависимостей нет. Другие allocated
sections, suffix multiply/divide и M4/generic compile controls совпали.
Это не новый production link или оценка итогового Flash после GC.

Текущий source SHA:
`9501eb31af70a512308d2ebb4cac2c37e425f6c7c5477ad8d884b28a12707e89`.
Diagnostic ELF:
`7fdb42ab072e1e70f0a6db32187228935b63a498e95eddc35b4df02d1065790a`.
Full object:
`0964ad58abf6cd4666ed305faf1b38e101db2b6a815961019602f545e70bac01`.

Дельта для review — `subnormal-input-only.patch`; full private source —
`native_eabi_m0_rp2040.S`. Предусловия и границы аргумента — `PROOF.md`;
текущие результаты — `qualification.json`, `controls.json`,
`object-isolation.json`, `body-equivalence.json`; входы — `input-pins.json`.
Первый smoke до cell shortcut сохранён как исторический trial; его22
проигрыша устранены текущим кодом и не считаются финальными результатами.

Независимый GO этой дельты пока не заявлен. Утверждение о полном входном
домене относится к наличию корректных путей и source argument; универсальная
скорость на всех2^128 парах не доказана. Цель всей библиотеки не закрыта:
остальные функции, general pow с UDF, интеграция на принятую базу и physical
timings/IRQ/platform acceptance остаются. Firmware/version, canonical/Git,
USB/Flash не менялись, новые formal/platform pipelines не создавались.
