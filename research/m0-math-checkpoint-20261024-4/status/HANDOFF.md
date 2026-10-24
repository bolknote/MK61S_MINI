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


## 2026-10-24 bounded atan residual repair, private author result

The new immutable inspection packet is `.build/m0-atan-residual-original-goal-20261024`. The four previous expanded speed inputs now cost READY1568/1555 and DIRTY1750/1725 versus correct Qfplib1783-1791. Exact residual arithmetic needs71 bits; no new tables, global RAM or libgcc. Code+444 bytes; observed stack888 versus872 parent. Generic M0/M4 allocated controls and whole independent public ELF relink pass.

Fresh65,416 public cases,228,332 public ARM calls and30,408 helper ARM calls have zero own errors. Measuring every observed CORE route adds176 ARM calls and exposes eleven previously unprofiled, preexisting raw atan deficits (22 state rows). The combined speed set has32,124 state cases; all5760 raw incorrect Qfplib functional outcomes remain retained. Zero losses on the old32,084-row speed subset does not mean atan is complete. Ordinary accepted-parent paths add1-10 instructions (mostly5-6), while all measured cases remain no slower than V164. See speed-proof.json and NEXT.md. Independent review is not claimed.

The historical507 matrix remains unchanged; whole math accuracy/speed, pow totality, repaired-base integration and physical acceptance remain OPEN. No further Git, canonical or hardware action was taken.


## 2026-10-24 all-geometry child and full profiling

Parent71-bit residual narrow independent GO verified at `.build/m0-atan-residual-independent-20261024/FINAL-REVIEW.json`, SHAb6a2234936391b97077999065e3055fd28e1935e519fd603a6a008c9d44bbaed. Parent source held unchanged. New immutable child `.build/m0-atan-residual-geometry-20261024` has79,096 fully profiled public cases/316,384 ARM plus30,412 helper ARM, zero own errors. Geometry extension adds32 code bytes, zero tables/globalRAM/dependencies; generic M0/M4 and whole public recompile/relink equality pass. Six raw Qfplib deficits improve. Full profiling exposes23 parent/17 candidate deficits, zero newly introduced. Keep17 OPEN; do not reuse old sparse speed counts. Regressions against V164 are retained (four raw inputs/eight state rows).

A separate ninth-order study has a directed-MPFR-tested model with exact all-geometry error<3Q70 and an isolated117-121-instruction ARM correction kernel (8,586 calls). It is not integrated and can exceed the observed remaining instruction budgets. NEXT.md plus cheap-design-certificate.py/bounds contain a cheaper, unimplemented strategy using known division remainders, a Q16 ninth term and an inverted low64 residue predicate. These are design bounds, not a runtime or whole-atan GO. Original full math goal remains OPEN; no canonical, Git or hardware actions.


## 2026-10-24 directional ninth-order repair, checkpoint3

The reviewed geometry parent remains immutable (receipt20f3a52335bf160c89b02bcf25262b4a5306e29cbbe0b61da94e284e8b6ba1fc). A separate child `.build/m0-atan-directional-ninth-20261024` implements the cheaper directional design: rounded residuals, exact division remainders, a Q16 ninth term and an inverted low64 residue predicate. All106,312 public state cases are profiled,425,248 public ARM calls plus75,298 bare helper calls; fresh MPFR and unbounded rational checks find zero own errors. All old17 raw deficits improve in both states. The larger corpus has20 parent/2 candidate raw Qfplib deficits;18 resolve,0 newly introduced. Remaining3FEF1BCDCF0D1830/BFEF1BCDCF0D1830 still refine through CORE-MATH. All four state losses and all regressions remain retained. Code+400 bytes versus geometry; stack912 versus888; no new table/globalRAM/libgcc, genericM0/M4 controls equal. Independent review/combined production/hardware GO are not claimed. This author packet is held unchanged. The historical507 matrix remains unchanged:292 resolved in separate candidates,215 historical deficits in pow/exp/ln/sin/cos remain; expanded atan counts are separate. User requested an intermediate Git checkpoint, without runtime integration or hardware work.


## 2026-10-24 small-h atan gate, no observed correct-Qfplib loss

Private frozen child `.build/m0-atan-tight-ninth-20261024`: exact one-sided small-h bound, sourcea85bbc49f2366ae64d025b36dfd27e86abf63c118e447cd43cedd060cdf87e2e, ELFfce98d75c6a88d57282b74798371c9c990029193741c4a986483a273321a50c9.116376 fully profiled state cases/465504 public ARM plus75298 bare helpers, zero own errors.107539 correct-Qfplib state cases faster/3equal/0slower. The two last raw inputs matchQfplib1787DIRTY; BFABB0EDC0AE5C6F now also equals1804. Code+60/stack912same/no new data or dependencies, M4/generic and whole public ELF recompile controls pass.132 parent regressions of1-7instructions are retained; four V164-regression state cases have incorrectQfplib answers. This is not exhaustive binary64 performance or independent/production/HWGO. Historical507 matrix remains unchanged. Separate ln cold-entry and exact dirty-ratio prototypes have only114-case probes; full helper/broad/isolation checks remain. No new Git/canonical/device changes. Original whole math goal remains OPEN.


## 2026-10-24 exact dirty log quotient, frozen author result

`.build/m0-log-ratio-dirty-20261024`: reuses existing log10 reciprocal, exact3-bit remainder correction, busy-zero and two dyadic endpoint shortcuts.29814 fully profiled publicln statecases/119256 publicARM plus155608 bare helperARM=274864, zero errors. HardwareREADY all14907 counts unchanged. DIRTY12893 faster/2014equal/0regressions. CorrectQfp deficits8310→27 inDIRTY, READY27same;8283expandedstate deficits resolved,27raw/54state rows remain. ln(2)DIRTY1250→612 vsQfp711. Code+164 object/+160linked, publicstack488same, helper68. Alltables/RAM/deps unchanged, genericM0/M4 controls and wholepublicELFrebuild pass. Seedcapsule184bytes assembles byteexact. ParentV164 and previouscheckpoints unchanged; independent/production/HWGO not claimed. Historical507 matrix not altered. Next separate prospective enclosure study proves RPmain7.897373<8 and near3.685012<4; those tighter runtime gates are not included. Original fullmath goal remains OPEN.


## 2026-10-24 RP ln strict-radius child, frozen author result

`.build/m0-ln-enclosure-20261024`: main7.897373<8/near3.685012<4, strict integer guards and negative n128 half-cell through certified general kernel.39318 profiled statecases/157272freshARM/MPFR0errors, all29814parentcounts reproduced. Five historical ln10 deficits resolved, old27raw14resolved. Expandedparent136READY139DIRTY→candidate31/34,105rawfixed/0new;34raw65state losses retained. All18992parentregression states add1 instruction; allocatedbytes0/newdata0/stack568sameonexpandedcorpus. Otherallocatedcode/tables/deps and genericM0/M4equal, wholeELFrebuildexact, inheritedhelperclosureaddresses+bytesexact. Parentdirtyratio independentreceipt45d06d0b57246951d97059355a53bc7c6543bdf2afd989686b70845ccca74f6b verified/material_findingsempty. Newchild independentpending. Author separatecandidates297 ofhistorical507no-slower (292strict/5equal), reviewedcount292; historicalmatrixunchanged. No mergedlibrary/production/HWGO. Separate directionalstudy modelaccept13/28 or15/28 nearinputs; notimplemented, two declinedmodelresults incorrect so no blindreturn. FullmathgoalOPEN.

Независимый receipt strict ln enclosure прочитан: `be4ab2a8053c3686e797d5dbd33d8808e421cc763d0c0dcf9ff26ce7239f0006`, статус `COMPONENT_CODE_GO_STRICT_RP_LN_ENCLOSURES_AND_N128_DISPATCH_ONLY`, material_findings=[]; это узкий GO дельты, не whole-ln/library/HW. В отдельных reviewed candidates 297 исторических входов не медленнее корректного Qfplib; остаются210. Последний near-rounding прототип только собран, не квалифицирован и в результат не включён.
