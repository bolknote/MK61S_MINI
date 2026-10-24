# Прямое ускорение нужных операций: текущее состояние

Исходная цель сохраняется: скорость Qfplib или лучше, правильное округление
плавающих результатов, корректные EABI conversions, сохранение M4.
Это сводка математических дельт, а не новая прошивка или новый pipeline.

| Операция | Результат сейчас | Реализация |
|---|---|---|
| double + / −, mixed signs, gap2…54 | 17 старых slowcase быстрее корректного Qfplib. 10 807 целевых случаев без ошибок, 6769 быстрее V164 / 4038 равны / 0 регрессий. Независимый узкий review GO получен. Другие cold/fallback ветви ещё отстают. | Наша, Flash; private candidate |
| double + / −, верхний конечный exponent2046 | Все2071 целевые нормальные пары не медленнее Qfplib; обычные8692 same-sign случая сохраняют прежнюю стоимость. Всего11 018 случаев без ошибок; независимый узкий review GO получен. | Наша, Flash; отдельная дельта поверх mixed-sign |
| double + / −, малые normal1…54 и Inf/NaN | Новый WIP:762 прежних проигрыша устранены,44 455 случаев без ошибок. На9527 измеренных случаях9286 быстрее/241 равны родителю.2416 обычных/top контролей прежней стоимости.18 subnormal-input проигрышей остаются. Независимый узкий review GO получен. | Наша, Flash; отдельная дельта поверх top-normal |
| double → uint32 | Все 256 старых valid slowcase:20–22 инструкции против43/Qfplib и47–50/V164. 47 966 случаев, integer+MPFR, без ошибок. Независимый узкий review GO получен; production integration не заявлена. | Наша, Flash; отдельный private candidate |
| general pow | Без изменений. Завершение последнего резервного пути для всех входов не доказано; UDF остаётся. | Наша + CORE-MATH, Flash |

Две исходные дельты mixed-sign и uint32 обгоняют Qfplib на273 входах из старого списка507 в
своих отдельных диагностических ARM объектах. Итог исторической матрицы
V164 не изменён. Полный набор ранее неизвестных отставаний не перечислен;
новые целевые тесты сохраняют обнаруженные проигрыши неизменённых ветвей.
Цель всей библиотеки поэтому не закрыта. Число инструкций не является
измерением физических тактов.

Для dadd/dsub независимый receipt:
`.build/m0-mixed-sign-original-goal-independent-review-20261023/receipt.json`
SHA-256 `772e806942517f65977d91dbeb50c493306be6e99ea388a94dd058b66ecf2bd9`.
Статус `MIXED_SIGN_DELTA_TECHNICAL_GO_NOT_PRODUCTION`, blockers пусты.
316 unique inputs /1298 ARM-вызовов с собственным Fraction RNE, READY/DIRTY;
0 ошибок. Все17 подтверждены быстрее. Независимая сборка дала тот же full
source object SHA `c0c4858ea1eceb875f10f9b275028d10f4a2f1a70778731db4704d8836ec5233`.
Receipt прочитан и его SHA сверен. Сам reviewed target остаётся неизменным.

Дельта dadd/dsub:
`.build/m0-mixed-sign-original-goal-20261023/HANDOFF.md`
SHA `67b94bd5e403cd3a0ab82f708da2f5eeaf85e79934fd1232b1c343ac4ff91e5c`;
`result.json` SHA `5b1fa3434b9bd887115a2e00926ae48ec8d924d382c6926d9f06a15fdf8a83d5`.

Дельта uint32:
`.build/m0-u32-original-goal-20261023/HANDOFF.md`
SHA `aa6f45d43388c94298dbd2ed5be220daa98842e1d3b50cdddfc2128d2ca7cd51`;
`result.json` SHA `1d4e45dbd257d8fbf33bf9516a966fb74bbbdf33145d3448be1a95175d3f1c8c`.

Независимый uint32 receipt:
`.build/m0-u32-original-goal-independent-review-20261023/receipt.json`
SHA `a0ebd2d0b56f33db311c11cbdc01cc3a4092b648ec9617f196a28f85f1ba19c3`.
Статус `D2UIZ_DELTA_TECHNICAL_GO_NOT_PRODUCTION`, blockers пусты.
SHA и статус прочитаны/проверены. Это GO только этой математической дельты.

Новая верхняя ветвь находится отдельно:
`.build/m0-mixed-sign-top-normal-20261023/HANDOFF.md`
SHA `d938a6627f79d76593e4f00ba02f9a0f750d553eb9abc138c5fb128bf5da50d3`;
`result.json` SHA `6e4e5b7eafeea3a11eebb499860f53d1d51fe892ce47b325ae4e48ae90f7d11d`.
На её целевом наборе2221 случая быстрее родителя,8797 равны,0 медленнее;
2051 прежнее отставание от корректного Qfplib устранено. Эти случаи из
расширенного набора; их нельзя прибавлять к историческим273 из списка507.
Стоимость —232 байта кода, без таблиц/RAM и без прибавки инструкций обычному
сложению. Глубина fallback-кадра остаётся24 байта. Родительский пакет не менялся.

M4 soft/hard и generic M0 compile controls сохранены. Математические ROM
вызовы новыми дельтами не добавляются; captured ROM используется при
проверках прежних служебных fallback функций. Таблицы/global RAM не растут.
Кодовые spans в контрольных объектах: −116байт dadd/dsub, +54байта uint32;
это не замер итогового Flash после линковки.

Независимый top-normal receipt:
`.build/m0-mixed-sign-top-normal-independent-20261023/FINAL-REVIEW.json`
SHA `1fa5ec2420e2ddf1a8d8a1ca881976f4c0033f308d601dd7d99b12afad58b86f`.
Статус `TECHNICAL_GO_TOP_NORMAL_DADD_DSUB_DELTA_ONLY`, blockers пусты;
receipt и SHA прочитаны/проверены. Это узкий GO дельты, не production/hardware.

Новая low-normal/Inf/NaN дельта:
`.build/m0-add-cold-normal-20261023/HANDOFF.md`
SHA `b4a976a59d040184a709dc48216210be0c7be129be62b74a1017661a5f08dd1b`;
`result.json` SHA `70014f74e93ddf39ff37a1001a56601c85e16dcd89a22b3e0dbbce1f3f5a5bdb`.
Блок+324 байта, в том числе8 байт IEEE literals, без таблиц/RAM/новых
зависимостей. Raw NaN sign/payload policy прежний, ordinary/top controls
равны по инструкциям. Проверенные обеими эталонными реализациями остальные
normal-пути ускорены. Непрофилированные случаи не используются для speed claim.

Следующие стадии исходной задачи: review E0/subnormal-input дельты, интеграция принятых
математических дельт на утверждённую исправленную базу; оставшиеся медленные
ветви нужных операций; practical general pow; физические такты и аппаратная
приёмка по существующей очереди. Новая product feature для этого не требуется.
CALCAP и дополнительные unused float/FMA, d2f/f2d, pow-subset исследования
не возобновлены. Canonical source/Git/USB/Flash и frozen V164 не менялись.

Независимый low-normal receipt: `.build/m0-add-cold-normal-independent-20261023/FINAL-REVIEW.json`, SHA `1266ecde350f8eb7662cc335da11ad7aece6e2cb18d36ed9d723bbac3c9edd2d`. Статус `TECHNICAL_GO_LOW_NORMAL_AND_NONFINITE_DADD_DSUB_DELTA_ONLY`, blockers пусты.

Новая E0/subnormal-input дельта: `.build/m0-add-subnormal-input-20261023/HANDOFF.md`, SHA `7b503ade4ce2c72bff8292ac526f6d8866de4003262f60f35e59ee74cf5fc149`; result SHA `4cbf5c03c4846ca4f653700d293801d6234fe79ec5459994d7aabe0a671136fe`. 70 261 случай / 210 783 ARM-вызова, без ошибок; 3015 профилированных: 2623 быстрее, 392 равны, 0 регрессий. Все18 прежних проигрышей устранены (20.89 против64.78 инструкций Qfplib).1768 unaffected controls равны по результату и инструкциям. Самостоятельный assembly без C++ fallback/ROM,20 байт стека,+268 байт кода. Независимый review пока не заявлен; полная матрица и физические такты не проверены.

E0/subnormal-input independent receipt: `.build/m0-add-subnormal-input-independent-20261023/FINAL-REVIEW.json` SHA `d7c8509fc3d9e8f375fd612840c7e4935abd9117cba183edf6b091e958a69446`, status `TECHNICAL_GO_E0_SUBNORMAL_INPUT_ZERO_DADD_DSUB_DELTA_ONLY`, blockers0; source/receipt прочитаны и SHA сверен. Research checkpoint `31fc77615224b0f66d3df820fd2f9228078fb1bc` сохраняет предшествующий pending snapshot и не переписывается.

Новая l2d entry дельта `.build/m0-l2d-original-goal-20261024/HANDOFF.md`: все16 старых проигрышей устранены (12 быстрееQfp/4 равны),30222 cases/90666ARM без ошибок,6899 быстрееродителя/23323 равны/0 медленнее,+8B,0stack,публичные884BравныbareELF. Independent review pending.

Новая sqrt cold дельта `.build/m0-sqrt-cold-original-goal-20261024/HANDOFF.md`: +Inf12/15/12 инструкции (candidate/V164/Qfp),15136 cases/45408ARM безошибок,7960 быстрее/7176 равны/0 медленнее,−8Ballocated,tableaddresssame,normal/signedzeroexactcost. Independent review pending.

От старых507slowcases в отдельных private candidates теперь290 no-slowerQfp (285strictfaster/5equal); это не merged library result. Остаются217: pow=153, exp=16, ln=10, atan=2, sin=22, cos=14. Историческая матрица не изменена.

Независимые l2d и sqrt-cold receipts прочитаны, SHA/blockers проверены: l2d `fa009ccbe011ae9ec0976eca503aa35abddbc8395feb376fd8e26accb429dae2`; sqrt `7aff3bf10d98b3d184d0708d7ae212be45225e1ced8a13ccdc23d4e233d74300`. Оба narrow TECHNICAL_GO; reviewed targets/commit31fc не менялись.

Новая atan packing дельта `.build/m0-atan-original-goal-20261024/HANDOFF.md`: старые2losses→READY1362/1304 противQfp1796; DIRTY1548/1470.58276publiccases/199772ARM безownederrors,24944profiled:24498faster446equal0slower,−96B/no newtables. Но4новыхрасширенныхвхода(2magnitudes/обаsign) всёещёCOREslow; wholeatanнеготов. В remaining-slower.jsonсохраненыобаSIOstates. Независимыйreviewpending. В отдельныхкандидатах292изисторических507no-slower(287strict/5equal),остальные215исторических+4расширенныхatanнельзяскладыватькакобновлённуюматрицубезmergereplay. Fullgoalactive.


## 2026-10-24 intermediate commit checkpoint

The frozen atan packing delta now has independent narrow technical GO; receipt SHA256 `320ba7d86efaae128e9e98f0e8dd1c35297ad393b4dfdc2d7513e505d3006f29`. Its four expanded speed deficits remain in the frozen result.

A separate mutable residual-repair prototype reduces the four DIRTY cases to 1800/1800/1775/1775 instructions versus Qfplib 1784/1791/1783/1790. This is only a 27-row public probe. Two still lose by 16/9 instructions; full corpus, current object isolation and independent review are outstanding. Exact Fraction enclosure is below6 Q70; a fresh actual-ARM helper check passes30408 calls covering all bounded quotient magnitudes0..33. No new tables or global RAM. Source and evidence are saved as WIP, not promoted.

This checkpoint does not complete the original math goal or integrate any delta into the canonical runtime.
