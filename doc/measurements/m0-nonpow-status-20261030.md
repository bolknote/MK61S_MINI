# M0+ non-pow: состояние на 30 октября 2026

**BASE полностью измерена и независимо принята Root: 505 пакетов, 22 065 строк, собственных ошибок округления 0. NEXT записана, полный2МиБ readback совпал, успешный boot и typed-состояние подтверждены отдельным observer; первые4 пакета NEXT приняты, ещё28 имеют полные raw/COMPLETE из TX-cap HOLD; всего32 отчёта/4748 входов, ownwrong0/Qfplibwrong0. Для28 требуется свежая typed-проверка после остановки;473 пакета ещё не запускались.** `pow` не меняется, M4 не затрагивается.

Проверены все 21 699 исходных входов и 366 дополнительных одиночных точек. Это конечная проверка, не доказательство правильного округления для всех binary64. У Qfplib и явно помеченных композиций — 1827 неверных ответов с учётом повторных точек; их результаты и время сохранены как диагностика. Составные asin/acos/log10 сохраняют пометки `qfplib_composition`, формулы и области применения.

## Что показала базовая сборка

На исходной матрице из 108 групп с правильным эталоном наша медиана ниже в 107. У f2d normal медиана выше на 0,28%, но диапазон разностей пересекает ноль. Дополнительные точки специально выбраны из прежних проигрышей и неблагоприятных изменений; их нельзя считать случайной выборкой всех вызовов библиотеки.

Во всём наборе 505 пакетов основное сравнение допустимо для 463 групп: 143 медианы ниже Qfplib, 320 выше; у 10 диапазон пересекает ноль. Неопределённые ID: 42,46,47,176,177,178,179,180,183,186. Время ID144 исключено отдельно от его подтверждённой битовой корректности.

Примеры проигрышей **BASE** на специально выбранных одиночных входах, RP2040 125 МГц; TIMERAWL измеряет микросекунды, не циклы:

| Функция / входы | Наша, мкс/вызов | Qfplib, мкс/вызов | Наблюдаемый проигрыш |
|---|---:|---:|---|
| sin/cos145..168 |17,241–25,074|12,967–13,101|1,325–1,922 раза|
| exp169..172 |24,079–24,532|6,440–6,834|3,590–3,739 раза|
| ln284..289 возле единицы |22,065–26,419|7,276–7,719|2,872–3,565 раза|
| atan290..291 |32,962–33,310|17,480–17,483|1,886–1,905 раза|
| dadd292..304 |0,811–0,962|0,721–0,856|1,089–1,134 раза|
| dsub305..308 |0,785–1,060|0,702–0,912|1,090–1,163 раза|
| d2uiz189..308,343..504 |примерно0,585–0,619|примерно0,480–0,505|примерно1,16–1,29 раза|

Все эти сравнения сохраняют правильность обоих ответов. Среди l2d есть выигрыши и малые неопределённые различия. В диагностике оставлены и tan около77/73 мкс против15 мкс у Qfplib, но там эталон неверен, поэтому они не включены в основное сравнение скорости. Диапазоны эмпирические, не доверительные интервалы.

На обычных группах BASE быстрее, например: sqrt normalized1,283936 против1,361694 мкс; mul full mantissas1,189453 против1,231812; div full mantissas1,483521 против1,540771; add mixed-sign1ULP0,992432 против3,597290. Эти результаты не заменяют проверку остальных входов.

## Полнота и исключения

505 APP и 505 COMPLETE выполнены ровно по одному разу, плюс 5 служебных записей: всего1015 файлов ledger. Фактические публичные вызовы обеих библиотек —49 755 454, control-вызовы —23 301 912. Все RAW, strict-decoded JSON, контрольные измерения, cache-счётчики, проигрыши и неопределённые диапазоны сохранены.

Полный role bridge явно разделяет492 обычных PASS completion и13 исключений: ID0 получен поздним чтением после штатного FLOW0; ID133..143 — принятые отчёты частичного HOLD с последующей проверкой неизменности данных; ID144 — позднее чтение с `primary_speed_accepted=false`. Старые HOLD и once-записи не переписываются. Для чистого HOST aggregate прошли17 новых целевых проверок; первые13 проверок фазового обработчика также прошли. Это ещё не готовый аппаратный допуск на NEXT.

Во время ID144 пользователь нажал SHIFT, physical counter0 стал2. Отдельное чтение подтвердило неизменность данных, программы, IP, настроек и домена часов; Root отдельно принял текущее counter2/epoch24. Время144 остаётся исключённым: пересечение события с измеряемыми интервалами неизвестно. Последующие scopes145..504 завершены при стабильном counter2, RTC_SET0 и settings sequence331; все собственные процессы закрыты, внешние пробы ESRCH.

Основные HOST артефакты в `.build/m0-nonpow-next-transition-20261030-001`:

- `BASE505-RAW-SUMMARY.json`:696943B, SHA1979b9846e7f9583adee8b386c641bfb22cdb6cdbca580bb02cb71e3e9a67d0b.
- `BASE505-ROLE-MANIFEST.json`:176367B, SHA05894ac9f0f1c6ba331d8fb04418b112357029ab681d262090e82edbc18ac420.
- `BASE505-ROLE-VERIFICATION.json`:1121B, SHAe6b97dcf72a0d74b1b95d6e2d441a8e4a4b5ce9ac8bba933e701357856604df8.

Последний BASE scope465..504: POSTEXIT `ce9c6f5e…`, RESULT `d633ff5d…`, ACTUAL-EXIT `a1b7f07a…`, after-state `58a06bae…`; Root close `00327fe6…`.

## Новая версия и M4

На замороженной финальной SDK-сборке для21 699 исходных входов собственных ошибок0. Среди19 882 правильных эталонов:19 251 быстрее и631 равно по числу ARM-инструкций,0 медленнее; BASE имела18 921/629/332. Это HOST-подсчёт инструкций, не аппаратное время. Все332 прежних проигрыша и34 представителя неблагоприятных изменений включены в физический набор, чтобы проверить NEXT на тех же входах.

Финальный HOST пакет содержит220 461 научный ARM-вызов с MPFR4.2.2,349 657 базовых/преобразовательных проверок,73 990 FMA-троек ×3 состояния SIO, дополнительные трудные входы и54 672 проверки возле77 границ; собственных ошибок0. Физический caller не заявляет прямого сравнения FMA: нативной FMA у Qfplib нет.

Пять disabled genericM0/M4 контролей совпали по выделенным секциям, символам и смысловым релокациям. Принятые изменения ограничены12 M0 математическими путями. Сохранена таблица4КиБ без роста статической RAM; production text+224B, bin+48B. Две SDK-сборки заморожены, новых сборок в этой аппаратной фазе нет; undefined/libgcc members0.

## Остановка при переходе к NEXT

HOST successor с62 целевыми проверками был принят Root. Один фактический переход ROM001 остановлен: `No ROM handoff within8s`; передана одна последовательность RS/C5/!, записи Flash не было. Supervisor84355 и actor/group84361 завершены, внешние пробы ESRCH. Старые1015 записи и original4c сохранены; добавлена только consumed `ROM-next`, всего1016. `PROGRAM-next` отсутствует. HOLD/claim повторно не используются.

Причина по pinned source: `main.cpp496` разрешает RAW `!` только при `!services.active()`, то есть CLOSED. Наш последний кадр перед `!` подтверждал RAW, но активный собственный VIEWER. Контроллер правильно проверил RAW, однако не учёл дополнительное firmware-условие CLOSED. При неизменном состоянии `!` маршрутизируется как USB-key21 в finished CONSOLE и игнорируется; возможны activity/tone/controlpulse, но не физическая клавиша и не запуск ROM. Это объяснение по исходникам, не утверждение о непрочитанном состоянии после HOLD.

Хронология подтверждена byte offsets в raw-потоке: status201 COMMAND34950 (crash getter), status101 COMMAND38884, status102 RAW42285 (после RS). RX_USB1312915→1312927→1312929. Номер201 не означает более позднее время. Root отдельно принял исправление хронологии и закрыл HOLD; OS пока видит прежний normal USB, но это не заменяет ответа firmware.

Подготовлен только один C5 без переключения режима: `.build/m0-nonpow-rom-hold-probe-20261031-001/READY-QUALIFIED.json`, SHA054fadcf5b6b42e219d8e7889f4d9e84f431413abc5014c6d43ef7a528c8da99.13 узких HOST-проверок прошли. По отдельному Root Go исполнен один C5: TX1/RX3397, exact RAW/ownVIEWER/BASE/epoch24/RTC0/counter2/RX1312931/domain4c. Supervisor89276/actor+group89277 закрыты, старые1016 ledger неизменны; Root независимо принял actual read. Нового UI/ROM/Flash допуска этим чтением нет. Ограничения: TX1,60с,0CLI/US/RS/!/keys/Flash/tool/APP/SD/setters; BASE/RAW/ownVIEWER/epoch24/counter2/RTC0/4c и RX_USB1312931. Полные данные калькулятора этим чтением не перепроверяются. Уточнённый source-backed путь здесь — ровно два ESC: terminal OPEN_FILE.APP каждый раз вызывает open(EXPLORER)→browse(CLOSED), устанавливая browser_parent=CLOSED и очищаяfilter; run_native не меняет directory/. Поэтому VIEWER→BROWSER→CLOSED, а не условные три ESC из раннего проекта. Пакет `.build/m0-nonpow-owned-viewer-close-20261031-001` прошёл15 текущих HOST-контролей; READY `609f8b5e…`, operator `1b19f275…`. Точные C5-фазы и RX, errors/settings/domain до клавиш; после CLOSED — narrow source0 guard, qualifiedUS и original typed capture/P2 comparison. Создаётся один новый UI-close once slot; старый ROM-next не переписывается. По отдельному finiteGo исполнен ровно один CLOSE001: два USB Esc дали точные фазы VIEWER→BROWSER→CLOSED, затем qualified US и исходный typed capture подтвердили identity, reg/stk/hout/pwd/alarm/IP/settings/epoch/counter и домен часов. Terminal COMMAND, BASE6EFB39C9/E8E2D2E8, epoch24/counter2/RTC0/settings331. TX54/RX48596; физических клавиш, ROM/Flash/APP/SD/setters0. Supervisor92793 и actor/group92794 завершены, внешние kill0 ESRCH. POSTEXIT `31d7c0e9…`, RESULT `3fb5c71d…`, ACTUAL-EXIT `65598e53…`, after-state `52315001…`. Добавлен ровно один `OWN-VIEWER-CLOSE-NEXT-001`, старые1016 ledger и origin4c точны; всего1017. Root независимо принял actual CLOSE001: `ROOT-PICO-OWN-VIEWER-CLOSE001-ACTUAL-CLOSE-001.json`,3037B/SHAe5c569b2b68361f183121a1a213c1beb3ab434482f8c14b631346f503619d3d2; проверены1064 ссылки, три RAW-фазы/RX, два Esc/один US, typed-сравнение и процессы. Нового ROM/Flash допуска этим закрытием нет.

## Что осталось

1. Независимый Root actual-close CLOSE001 получен (`e5c569b2…`). C5-наблюдение, закрытие двумя Esc и последующая полная typed-проверка выполнены. CLOSED достигнут; прежний ROM001 HOLD/claim сохранён.
2. Отдельный явный ROM-переход из подтверждённого CLOSED квалифицирован в `.build/m0-nonpow-closed-rom-20261031-001`: 26 текущих HOST-проверок прошли, READY `57eefdba…`, operator `b9202787…`. Новый фиксированный once `ROM-NEXT-CLOSED-002` создаётся после полной typed/crash проверки до RS/!; прежний ROM-next не повторяется. Исходные QualifiedClosedWake/preflight/capture/crash/raw_transition сохранены; narrow own released CLOSED/source0/path guard проверяет firmware-условие `!services.active()` вместе с RAW. Полный BASE role bridge остаётся. Root HOST review `8ab5ce18…` проверил все260pins/2999282B и26 HOST-контролей. Первый новый Go `646f0863…` исполнен один раз (exec9e5d24), но неизменённый LiveLease отклонил actual enabled grant `895f4e9a…`: в нём остался `HOST_FIXTURE_ONLY=true`. Это preopen-ошибка до parent/supervisor/CDC/once; deviceIO0, все1017ledger точны, новый `ROM-NEXT-CLOSED-002`/PROGRAM-next и stage outputs отсутствуют. Exact grant/Go и receipt сохранены в `host-receipts/CLOSED-ROM-002-PREOPEN-EXIT-001`, INVOCATION-EXIT272388B/SHAf8aa957dc0d6ae40ca1ee50dc8ecad92727e46f64f5b0902416ce2edf13c190b. Root закрыл preopen-сбой (`23c7190a…`) и выдал отдельный corrected Go003 `455c2333…`/grantR2 `cd8fd7b7…` с HOST_FIXTURE_ONLY=false; настоящий LiveLease constructor/guard и proof проверены Root. Первый CreateProcess завершился timeout permission review до создания процесса; отдельный HOST-check подтвердил отсутствие outputs/claim и195s остатка. Один явно разрешённый системой creation retry exact argv успешно выполнил единственный device stage (exec335194/session62721/exit0). Повторной команды устройству не было. Operator/READY/FROZEN без изменений.
3. Новый ROM-переход фактически PASS: TX65/RX49193, qualifiedUS1/RS1/!1/ESC0; original typed/crash exact, COMMAND и RAW C5 оба CLOSED/source0. Получен полный `Entering RP2040 USB BOOTSEL`, затем native disconnect errno6. Supervisor96803 и actor/group96806 завершены/reaped/gone/resourcePASS, внешние ESRCH. POSTEXIT `ad5c2c41…`, RESULT `895b032c…`, ACTUAL-EXIT `c566cf72…`, typedstate `88013713…`; новый once `dbbe350d…`, всего1018ledger, все старые1017 byteexact. ROM UID ещё не подтверждён инструментом; PROGRAM-next отсутствует. Root независимо принял actual ROM handoff (`591783be…`,1067refs/1412637B); OS видит VID2E8A/PID0003/location18022400/USBserialE0C9125B0D9B, tool UID pending. Новый data-only PROGRAM PREGO `.build/m0-nonpow-next-program-prego-20261031-002` готов: READY `80492a6d…`,82pins/9748351B, original successor.proof с новым actual ROM PASS; original writer/source не менялись. Disabled template HOST=true, Root-required actual=false и real constructor/guard явно указаны. Root принял PROGRAM PREGO (`8dae9889…`) и выдал finiteGo (`8c7e6c41…`/actual grant `2f41ccda…`). Один запуск PROGRAM001 остановился до native load: original atomic_load.admit требует `inflight_load_policy`, которого нет в перенесённом шаблоне/actual grant. Это пропуск подготовки PREGO; pure successor.proof этот policy не проверяет. Info UID E6657CD423721C35/RP2040/2048K и полное чтение BASE8fd прошли. Ровно2 tool-процесса3064/3065 known0, Flash writes/load/boot0; PROGRAM-next consumed (`45d4680f…`) до admission, старые1018ledger точны, всего1019. Supervisor3058/actor+group3061/tools3064/3065 завершены/gone, externalESRCH. POSTEXIT `285d4547…`, RESULT `cff2c424…`, ACTUAL-EXIT `014a5156…`, BEFORE-LOAD-HOLD-AUDIT `7647fc16…`. Нет03nativepid/exit/streams/atomicadmission/afterFlash. Устройство остаётся в ROM, FlashBASE не изменена. Старый PROGRAM-next не повторяется; требуется отдельный Root HOLD-close и новое явное program-once disposition, с обязательным policy precheck до tools/claim. NEXT пока не записана. Root независимо закрыл pre-load HOLD (`dcf0f499…`,1045refs/3413793B) и разрешил только HOST continuation с новым фиксированным `PROGRAM-NEXT-PRELOAD-CONTINUE-002`, старый PROGRAM-next остаётся consumed/HOLD. Один новый frozen packet `.build/m0-nonpow-preload-continuation-20261031-001` готов: READY `fe60c7b1…`, controller `e1be2243…`,177pins/6800393B,39 targeted HOST PASS. Original programmer/ToolRunner/atomic/preflight/supervisor/old successor не менялись. Policy/expectedargv/whole210s проверяются доtools/newclaim; real unchanged atomic.admit+window испытаны приватно. Новыйonce и честная отдельная evidence-bridge для original NEXT observer/math проверены, RTC0/1+HOST-onlyepoch701 служат исключительно fixture. ActualNEXTepoch/RTC/counter не предсказываются. Все1019realledger иoriginal4c точны, deviceIO/native tools/realledger writes/builds/old suites0; Root получает один packet, подготовка остановлена для review. Root независимо принял packet (`a583988d…`) и actual constructor/guard/proof/runtimeprecheck210, затем выдал отдельный finiteGo (`bf7c68ed…`/grant `8db2a9d9…`). Один физический PROGRAM-CONTINUE002 завершён PASS: freshUID E665/RP2040/2МиБ; fullbeforeBASE8fd, soleloadNEXTc9ac, fullafter==c9ac побайтно, reboot known0. Supervisor8291/actor+group8302/native5 [8305,8306,8328,8383,8393] known0/reaped/gone, externalESRCH, no withdrawal/signals/orphans/grace. POSTEXIT `e8c7d186…`, RESULT `101ea298…`, ACTUAL-EXIT `08fb9c1e…`; newonce `965f9a16…`, atomicadmission `8c70fbca…` с exactPOLICY/argv/owner и226,324s остатка передload. Старые1019ledger точны, всего1020; oldPROGRAM-next/HOLD сохранены. NEXT теперь записана, но это пока exactreadback+bootrequest; actualepoch/RTC/counter/CRCframe и замеры не наблюдались. Root получает dossier для independentactualclose/newoncebridge и отдельного observerGo; Root независимо принял actual PROGRAM (`c6db4dd8…`,1063refs/5545164B, result+new_program_once). Затем отдельный observerGo (`c90b9c89…`/grant `236320c2…`) исполнен один раз PASS: actual NEXT D311DD79/CRC540DEFD8, epoch25/00010001, RTC_SET0/PPM0, physical0, settings331, COMMAND/CLOSED. Original full reader/data/settings/identity/domain проверки прошли; US1/TX50/RX39965, Flash/tool/APP/SD/setter/physical0. Supervisor10423/actor+group10430 known0/reaped/gone/resourcePASS, externalESRCH. POSTEXIT `6a36e39f…`, RESULT `3c8debd6…`, ACTUAL-EXIT `f24b75d1…`, currentstate `16a33b7e…`, initialframe `e9b92ab6…`. Все1020ledger точны, original4c сохранён; Root независимо принял observer (`06a23c49…`,1062refs); отдельный initialmathGo (`9206c0f2…`/grant `b674020c…`) исполнился один раз PASS. Четыре APP/COMPLETE NEXT000..003,93cases, ownwrong0/Qfpwrong0; eligible4/медианаNEXTбыстрееQfp4/неопределённых0. Actualpublic447274,controls195912,TX6274/RX136476. Nextsin10,6214565/Qfp12,9885142; cos10,6036736/12,9986440; tan10,1204067/15,2323616; i2d0,22558594/0,45532227 мкс. Отрицательные изменения к BASE сохранены:sinBASE9,113636→NEXT10,621456 (+16,54%),cos9,399408→10,603674 (+12,81%);tanBASE10,146497,i2d0,22644043. Сравнение версий из отдельных запусков; это не парный межверсионный доверительный интервал. Supervisor12241/actor+group12248 known0/reaped/gone/resourcePASS, externalESRCH. Typedдо/после точны:epoch25/00010001,RTC0,physical0,domain4c. EndownfinishedVIEWER/source0. POSTEXIT `0446ad07…`,RESULT `ac609ac3…`,ACTUAL-EXIT `bfa76209…`,after `af8741ea…`,lastflow003 `c2229296…`; старые1020ledger точны,всего1028. Всеraw/контрольные/cache/timing/adverse rows сохранены. Послеinitial4 остановка для независимой сверки; остальные501 NEXT ещё не выполнялись. Root получает actual-cohort для независимого acceptance и отдельного initialNEXT000..003 Go. HOSTepoch701 никуда не подставлялась. Загрузить уже собранную NEXT: полный образ c9ac1633569c551d39fa753033e74807462ee304cbb63eba09a0af9ea3ee76c7, buildD311DD79, CRC540DEFD8. Фактические epoch/RTC/physical counter после boot измерить; не подставлять предположение. Выполнить505 NEXT пакетов и сравнить с BASE/Qfplib, сохраняя все исключения качества и точности.
4. Удалить только собственный `/MK61S-M0-TIMING-NONPOW-20261030` с TIMING.APP/INPUT/RESULT. Исходные35 элементов SD не менять.
5. Вернуть исходные2МиБ Flash a05379163123d8f634ad1c81e82daf1d48afd5ea500139201f3503b96ee8f126 с полным readback, данные и исходную траекторию часов4c292b362e93c5dd3599000c0a089bfe199c46daf79ac69493b8ec8606bb6f2c. Две свежие резервные копии сохранены. Этот финальный возврат ещё не выполнен.
6. Интегрировать принятый результат, затем вернуться к `pow`.

BASE6EFB39C9/E8E2D2E8 подтверждена двумя полными чтениями2МиБ после исходного picotool SIGABRT. Его PROGRAM-base остаётся HOLD/consumed; повторной записи не было. Отдельный проверенный boot выполнен один раз. Исходная residentD6FABB43/EFBF5584 и исходный отсчёт4c никогда не заменяются более поздними наблюдениями.

## Проигрыши BASE по функциям

Это группы физического набора, специально дополненного трудными одиночными точками. Число групп не отражает частоту функции в приложении. Столбец неопределённых групп входит в число медианных проигрышей; эмпирический диапазон разности в них пересекает ноль. NEXT пока не измерена.

| Функция | Групп с медианой хуже Qfplib | Из них неопределённых |
|---|---:|---:|
| `f2d` | 1 | 1 |
| `sin` | 18 | 0 |
| `cos` | 11 | 0 |
| `exp` | 4 | 0 |
| `l2d` | 4 | 4 |
| `d2uiz` | 256 | 0 |
| `ln` | 7 | 0 |
| `atan` | 2 | 0 |
| `dadd` | 13 | 0 |
| `dsub` | 4 | 0 |

## Первые аппаратные замеры NEXT (000..003)

93 входа, своих ошибок0 и Qfplib ошибок0. Все четыре группы пригодны для основного сравнения; эмпирические диапазоны разности NEXT−Qfplib ниже нуля. Числа — мкс/вызов TIMERAWL, не циклы. Это ограниченный начальный набор.

| Функция, legacy | BASE, наша | NEXT, наша | Qfplib на NEXT |
|---|---:|---:|---:|
| sin,22 входа |9,114|10,621|12,989|
| cos,26 входов |9,399|10,604|12,999|
| tan,13 входов |10,146|10,120|15,232|
| i2d,32 входа |0,2264|0,2256|0,4553|

sin/cos медленнее собственной BASE; это ухудшение не скрывается выигрышем против Qfplib. Остальные501 пакет NEXT пока не измерены.

## NEXT004..067: остановка по лимиту TX и отдельное продолжение

Сегмент завершился HOLD NativeTXbudget, не COMPLETE: TX262132/RX978214. Полностью выполнены004..031 (28APP/COMPLETE,4655cases,ownwrong0/Qfpwrong0);032..067 APP не запускались, неопределённыхAPP нет. Последний wire `fsput data4512`96B получилACK4608/prompt; INPUT032 объявлен12320B,4608B точно совпадают с frozenprefix, end/commit не отправлен. Lastproven ownVIEWER031/status059 RX258312 +10144trailingTX => firstfreshC5expected268457. ПослеHOLD typedstate отсутствует. PIDs13832/13838/group gone/reaped, старые1028claims точны, всего1084. POSTEXIT `0241ff7c…`,RESULT `2faf37ba…`,ACTUAL-EXIT `fdd19df1…`,quality `6e96409f…`,audit `4a1abefe…`.

Все28primaryeligible,24медианыбыстрееQfp/4медленнее,эмпирическихпересеченийнуля0. Проигрыши: sinordinary13,50744/13,01488; cosordinary13,58801/13,02563; sinqfp_range13,57806/13,00957; cosqfp_range13,98611/13,02468мкс. Все11ухудшенийсобственнойBASE сохранены в полном сравнении; версии запускалисьраздельно. Эти28остаются partialHOLD evidence доfreshcheckpoint.

Один HOST packet `.build/m0-nonpow-next-tx-resume-20261031-001` готов: READY `5018f80f…`,controller `09667030…`,251pins/2942683B,32targetedHOSTPASS. Отдельный cancel/checkpointGo: exactfreshC5/RX/UID/4c, одинfsputcancel/новыйonce, originaltypedcapture+committedINPUT31/RESULT31/caller/rootentries. Затем отдельный mathGo: честныйpartialprefix+actualcheckpoint, стартunused32+, исходныеfullcaps4/16МиБ/20000commands/300s≤64APP и прежнийearly-returnguard. Frozenestimate старых4..67 TX966382>262144; будущих32..95 TX768860/RX5930668/4010commands. Rootgrants/canonical не включены; actualcancel/newAPP не выполнялись. HOSTphase остановлена дляreview. Originala053/data/ownSD/4c pending;pow/M4 untouched.

Root independently принял TX-HOLD (`7c0811ee…`,2649pins/5199935B,28rawreports заново decoded,fullTX/POSIXcksum/flows/claims). Actualafter не заявлено. Rootclose пришёл послеHOSTзаморозки, поэтому без перезаписистарыхFrozen/Ready/PREGO добавленыactual-HOLD-bounddisableddata+финальный manifest: READY-ACTUAL-HOLD-BOUND `fb6323bb…`,FROZEN `d4d940d4…`,PREGO `16a9c16c…`,259pins/3097741B. Pure actualboundhold_evidence2callsPASS,controller09667030и32targetedHOSTcontrols прежние. Actualdata/grants/canonical не включены; Rootreview pending.

## Фактическая отмена передачи 032 и проверка состояния

После Root HOST review `803836fb…` отдельный Go `cf03f4c3…` выполнен ровно один раз. Свежий C5 подтвердил RX_USB268457/SLEEP0, нужный UID, NEXT/epoch25, RTC_SET0, physical0 и settings331. Одна команда `fsput cancel` получила `@MKC:CANCELLED`; новый once `CANCEL-OWN-NEXT032-UPLOAD-001` потреблён. Незавершённая передача INPUT032 отменена, новые APP не открывались.

Полное typed-чтение подтвердило прежние регистры, стек, программу, IP, будильники, настройки и исходный домен часов4c. Побайтное чтение TIMING.APP и последних зафиксированных INPUT031/RESULT031 совпало. Имена, типы и размеры элементов корня вне собственного каталога не изменились; содержимое каждого пользовательского файла отдельно не перечитывалось. Старые1084 ledger точны, вместе с cancel-once теперь1085.

14 resident-команд, TX276/RX116428, Flash/tool/APP/math/setter/physical/US/RAW/ESC0. Supervisor21758 и actor/group21761 завершены с кодом0, reaped/gone, внешние проверки ESRCH. В `.build/m0-nonpow-next-tx-resume-20261031-001/outputs/tx-cancel-checkpoint-001`: POSTEXIT `e12d0f20…`, RESULT `6790f2ac…`, OFFLINE-AUDIT `e1e17a9b…`, current-state `201ed919…`; ACTUAL-EXIT в supervisor-outputs — `4e0bd14a…`.

Измерены32 из505 пакетов NEXT,4748 входов, собственных ошибок0 и ошибок Qfplib0. Результат004..031 остаётся partial/HOLD до отдельного Root acceptance checkpoint; исходный HOLD `2faf37ba…` сохранён. Первый неисполненный APP —032. Досье фактической отмены передано Root; следующий этап требует отдельного finite Go с исходными полными лимитами обмена. Возврат исходных Flash/данных/SD/траектории часов ещё предстоит; `pow` и M4 не менялись.

## NEXT032..064: нормальное завершение следующего сегмента

Root независимо принял cancel/checkpoint (`9e71df39…`) с явным принятием завершённого префикса004..031 и сохранением прежнего HOLD. Отдельный Go032..095 `fed60404…` исполнен ровно один раз. Исходный early-stop оставил время на возврат и typed-проверку: фактически выполнены032..064,33APP/COMPLETE;065..095 не запускались. Первый неисполненный APP теперь065.

13341 вход, своих ошибок0/Qfplib ошибок0. Все33 группы пригодны для сравнения;33 медианы ниже Qfplib, но у `f2d`046 разность времён пересекает ноль, поэтому выигрыш там не установлен. Примеры мкс/вызов: `i2d`0,226074/0,458374; `ui2d`0,188843/0,418457; `d2uiz`0,116943/0,497070; `ln` normal6,26294/7,43701, normalized5,97179/7,26727, near_one3,08289/6,54260, near_one_interval6,68093/7,47358; `atan` ordinary14,28243/17,56436, reduced14,44376/17,41539. Полные мантиссы `dmul` в группах059..064: наша1,18213–1,22620, Qfplib1,22998–1,26208. TIMERAWL измеряет микросекунды, не циклы.

Все изменения относительно собственной BASE сохранены отдельно: медиана NEXT выше BASE в034,050,056,062,063. В частности, `ln near_one_interval` BASE6,067655→NEXT6,680928 (+10,11%). Это раздельные запуски версий, не парный межверсионный доверительный интервал. Полное сравнение — `.build/m0-nonpow-next-tx-resume-20261031-001/host-receipts/NEXT032-064-BASE-QFPLIB-COMPARISON-001.json`,37824B/SHA6b8b6645017c70d619c6af0a27fbd0660a152a351c9d7fa01f4941d5254e42f8.

TX707983/RX2306088, public calls обеих библиотек3769940, controls1615488. Supervisor23878 и actor/group23902 known0/reaped/gone/resourcePASS, внешние проверки ESRCH. Typed-данные до/после точны, epoch25/00010001,RTC_SET0,physical0,settings331,домен4c сохранён. Старые1085 ledger точны, теперь1151. Новых Flash/tool/cancel/US/RAW/ESC/setter/physical действий не было. Последний own finished VIEWER —064, FLOW `12f3bc01…`.

Артефакты `.build/m0-nonpow-next-tx-resume-20261031-001/outputs/next032-095-001`: POSTEXIT `1891fab9…`, RESULT `1e3cf5c1…`, OFFLINE-AUDIT `5e234357…`, before `07cbd2ce…`, after `69fe0e15…`. ACTUAL-EXIT в supervisor-outputs — `26803bc9…`. Полное досье передано Root для независимой сверки и отдельного следующего Go. Итого NEXT65/505,18089 входов, собственных ошибок0/Qfplib ошибок0; осталось440 пакетов. Прежние проигрыши sin/cos и ухудшения относительно BASE сохранены. Исходные Flash/данные/SD/часы ещё не возвращены; `pow`/M4 без изменений.

## NEXT065..128 и проверка полного набора

Root принял032..064 (`4591ec38…`) и выдал отдельный Go065..128 `0aa7cd55…`. Он исполнен ровно один раз: все64 APP/COMPLETE выполнены, внутри сегмента неисполненных нет; первый неисполненный APP —129. 3105 входов, собственных ошибок0. У Qfplib1312 расхождений с точным эталоном в21 специально выделенной диагностической группе. Все43 группы с правильными эталонными ответами быстрее Qfplib; эмпирических пересечений нуля нет. Диагностические группы остаются в отчёте с явной непригодностью для основного сравнения скорости.

Примеры мкс/вызов: деление полных мантисс1,45605–1,62158 против1,50769–1,69446 у Qfplib; dyadic seed1,19104/1,49109; умножение на степени двойки0,34070/1,23560; `asin` ordinary21,0541/21,9347; `acos` ordinary21,32377/21,96124; `log10` ordinary7,99921/8,82186. Прямых одноимённых asin/acos/log10 у Qfplib нет: формулы эталонных композиций сохранены в decoded-отчётах. Изменения к BASE и все диагностические проигрыши сохранены, включая div both_short+2,30%, add equal_exponents+2,43%, diagnostic cos qfplib_range+20,27% и tan small_medium_remainder+21,11%. Раздельные запуски не дают парного межверсионного доверительного интервала.

TX182074/RX1093579, public calls обеих библиотек5869632, controls2131392. Supervisor25066 и actor/group25107 known0/reaped/gone/resourcePASS, внешние проверки ESRCH. Typed-данные, настройки и домен4c до/после точны: epoch25/00010001,RTC_SET0,physical0,settings331. Старые1151 ledger точны, теперь1279. Артефакты `outputs/next065-128-001`: POSTEXIT `37c255b1…`, RESULT `4acbd159…`, OFFLINE-AUDIT `9ed32161…`, after `bb1edcd2…`, последний128-FLOW `ccaad1db…`; ACTUAL-EXIT — `e16b5248…`. Полное сравнение BASE/NEXT/Qfplib — `host-receipts/NEXT065-128-BASE-QFPLIB-COMPARISON-001.json`,73264B/SHA47d22e323faac70b7f8f2afb8d60ad5846f73fab8cb8180cdbe6a94589f71c16. Root независимо принял сегмент (`9cd96ee0…`), заново разобрав64 raw-отчёта и151 статусный кадр.

Подготовлен отдельный чистый HOST barrier `.build/m0-nonpow-next-role-bridge-20261031-001`, без main/CLI, dispatcher, adapter, конструктора допуска, once-записей или обращения к устройству. Source `04b4c0aa…` требует477 обычных PASS и отдельно подтверждённые28 результатов прежнего HOLD004..031, точные Root checkpoint/cancel, все505 receipt/input/once/flow/raw/decoded, итоговый normal504 и исходный домен часов. Старые base/cleanup/restore/Q/T/R3/HOLD не менялись. Неполный disabled-manifest честно содержит129 результатов и376 оставшихся; статуса полного завершения ему не присваивали.

30 целевых HOST проверок прошли, в том числе реальная read-only интеграция с повторным strict decode всех129 аппаратных отчётов. Полная505-структура дополнительно проверена только на явно синтетической HOST fixture с заменой decoder исключительно в этом тесте; аппаратных результатов она не создаёт. Все1279 реальные ledger и original4c точны, ambient adapters не изменены, device/native/math/build/old-suite/real-ledger-write0. READY `29511253…`, FROZEN `986d2bd8…`, PREGO `ab219e55…`, qualification `e7fee79e…`;3093 local+38 external pins,13500452B. Пакет передан Root только на review. Финальные dispatcher/adapter, штатный выход VIEWER→CLOSED, cleanup/ROM/restore требуют отдельных точных доказательств и допусков.

Текущий аппаратный итог: NEXT129/505,21194 входа, собственных ошибок0/Qfplib1312 диагностических расхождений. Осталось376 пакетов и полный возврат исходных Flash/данных/SD/часов. `pow` и M4 не менялись.

## NEXT129..320: трудные одиночные входы

Три следующих сегмента завершились обычным PASS, каждый64 APP/COMPLETE без неисполненных пакетов внутри своего диапазона. Все данные/настройки/домен4c до/после точны, epoch25/00010001,RTC_SET0,physical0,settings331. Каждый процесс и группа закрыты с кодом0/reaped/gone/resourcePASS, внешние проверки ESRCH. Старые ledger неизменны:1279→1407→1535→1663. Все исходные RAW/контрольные/cache-измерения сохранены.

| Сегмент NEXT | Входов | Наших ошибок | Ошибок Qfplib | Пригодных групп | Медиана быстрее / медленнее Qfplib | Из них диапазон разности пересекает ноль |
|---|---:|---:|---:|---:|---|---|
|129..192|559|0|505|54|33 /21|169,171, обе `exp`|
|193..256|64|0|0|64|64 /0|нет|
|257..320|64|0|2|62|58 /4|307, `dsub`|

Дополнительные реальные проигрыши Qfplib не скрыты меньшим числом HOST-инструкций. В150,152..157,159..168 `sin`/`cos` занимают13,33362–13,61169 мкс против12,96228–13,10657: отставание2,31–4,67%. В169..172 `exp`6,67773–6,84485 против6,40625–6,83691;169/171 остаются неопределёнными,170/172 имеют положительный диапазон разности. В290/291 `atan`18,03577/19,23840 против17,47864/17,47888 мкс. В309 `sin`13,58459/13,00940;310 `cos`13,58728/13,02832.

Относительно собственной BASE сохраняются ухудшения: log10 diagnostic136/137 примерно+3,04%/+3,75%; sin/cos309/310 примерно+29,62%/+30,15%; reduced313..318 примерно+39,4–40,4%, хотя эти reduced-случаи быстрее Qfplib. Сравнение версий из раздельных запусков, не парный доверительный интервал. У BASE144 по-прежнему `primary_speed_accepted=false`: числовое наблюдение сохранено, `NEXT_over_BASE=null`, в основную скорость оно не попало. Все группы с неверными ответами Qfplib явно диагностические.

Артефакты в `.build/m0-nonpow-next-tx-resume-20261031-001`:

| Сегмент | POSTEXIT | RESULT | ACTUAL-EXIT | After-state | Последний FLOW | Полное сравнение BASE/NEXT/Qfplib |
|---|---|---|---|---|---|---|
|129..192|`3c33bd0b…`|`fa119494…`|`fe698dd8…`|`8df937a4…`|192:`9d9d403e…`|`f6239208…`|
|193..256|`d7d5d8ae…`|`2e503f72…`|`acc96d66…`|`053ee56e…`|256:`598779fb…`|`344d819e…`|
|257..320|`96d12332…`|`5e390783…`|`645bff22…`|`7ebb97f3…`|320:`82e66f9c…`|`6c91fdac…`|

Root независимо принял129..192 (`abf48ff7…`) и193..256 (`e0928320…`); досье257..320 передано на сверку. Для последнего сообщения потребовалась одна разрешённая повторная отправка: автоматический approval review первого сообщения завершился таймаутом; аппаратный прогон не повторялся.

Чистый next-role barrier принят только как HOST source (`92dd5a38…`), без разрешения его будущего исполнителя. Новый отдельный finalization packet `.build/m0-nonpow-finalize-20261031-001` пока черновик: final504/grant/state/Root acceptance перед любым I/O; отдельный штатный выход COMMAND→RS→VIEWER→BROWSER→CLOSED (RS1/ESC2/qualifiedUS1), свежий typed checkpoint; next-only caller к принятому барьеру и прежние cleanup/ROM/full original readback/once DATE/clock-return routines. Старые pipeline/base/HOLD/история не переписываются. Новый код в устройство не запускался, adapter не установлен; targeted HOST qualification/Ready ещё предстоят. Эта подготовка не останавливает последующие конечные math Go и не пишет текущий ledger.

Текущий результат NEXT321/505,21881 вход, собственных ошибок0, Qfplib1819 расхождений с точным эталоном с учётом фокусных повторов. Первый неисполненный пакет321, осталось184. Исходные a053 Flash/данные/SD/траектория часов4c ещё не возвращены; `pow`/M4 без изменений.

## NEXT321..448 и подготовка возврата

321..384:64 обычных APP/COMPLETE,64 входа, собственных ошибок0/Qfplib8. Из56 пригодных групп48 медиан быстрее и8 медленнее Qfplib; диапазоны разности этих8 положительны. Это sin/cos321..324,326..329. Диагностические tan331/333 с неверным Qfplib сохранены отдельно: NEXT84,88330/150,12830 мкс против15,22302/15,36768 у неверного эталона. В333 собственная BASE73,05005→NEXT150,12830 (+105,51%). У ln336..342 наблюдалось+24,3–25,4% к собственной BASE, при сохранении выигрыша против Qfplib;338 диагностический.

385..448:64 обычных APP/COMPLETE,64 входа, собственных ошибок0/Qfplib0. Все64 группы быстрее Qfplib без пересечений нуля; проигрышей собственной BASE в этом сегменте не наблюдалось. Оба сегмента сохранили typed-данные, настройки и4c: epoch25/00010001,RTC_SET0,physical0,settings331. Все процессы/группы known0/reaped/gone/resourcePASS, внешние ESRCH; ledger1663→1791→1919, старые записи точны. Root независимо принял оба сегмента (`953509a0…`, `f5565465…`).

| Сегмент | POSTEXIT | RESULT | ACTUAL-EXIT | After-state | Последний FLOW | Сравнение BASE/NEXT/Qfplib |
|---|---|---|---|---|---|---|
|321..384|`295b9baf…`|`2c1bde1e…`|`c2d40225…`|`b677cab1…`|384:`c9624e20…`|`2a215db7…`|
|385..448|`1ca9ac14…`|`5a117347…`|`c4f198d4…`|`e4a1c27a…`|448:`13dd8a16…`|`4fce5f97…`|

Последний Go449..504-001 (`f2f656e0…`) при первом чтении уже вышел за `must_start_before_unix`:1793420734,938327 против1793420696,7827652. Он не исполнялся: controller/native creation attempts0, CDC0, APP449..504 claims отсутствуют, actor/supervisor outputs отсутствуют. HOST receipt `LAST449-504-GO001-STALE-NOT-EXECUTED.json`,777B/SHA27d2e81fd04b8e8df5ba9547b999d3fde717129138d5acd3b15cee8192d10367. Root уведомлён для нового отдельного допуска; старый Go/история не переписывались. Текущий итог449/505,22009 входов, собственных ошибок0/Qfplib1827, осталось56 пакетов449..504.

Один disabled finalization packet `.build/m0-nonpow-finalize-20261031-001` заморожен и передан Root: READY `f727ad8e…`2580B, FROZEN `ae7f093a…`52162B, PREGO `0559c7ed…`13557B;136 local+42 external refs,7069294B. Источники finalize `a5050e52…`, contract `5f42680f…`, owned_close `e56f05d3…`; source-owned exit proof `c4a5db79…`. Все59 targeted HOST проверок прошли (`a98b6b6a…`460467B): реальные API enabled/disabled LiveLease на приватных canonical, отсутствие actual505/Rootreview отклоняется доI/O; emulatedRS1/ESC2/US1 с исходным typed capture; источник0/closed wake; ошибки UID/RX/physical/sleep/pages/errors/typed/revocation; исходный atomicargv/210s резерв; исходные диспетчеры/BASE route и восстановление adapters; отдельный синтетический тест связывания final504/grant/flow/currentdata/Rootattestation с spy принятого барьера. Эти fixtures не являются actual505 или аппаратным допуском.

Пакет не пишет текущий ledger и допускает независимые добавления Root math: прежний1663-префикс и original4c точны, audit device/native/realledger-write0. Старые Q/T/R3/base/cleanup/restore/clock/atomic/HOLD/история и purebridge04b не менялись. Шесть конкретных disabled argv и шаблонов остаются без actual505/state504/Rootacceptances. Полный барьер повторяется до close/cleanup/ROM; program/clock/verify связывают точное Root-принятие505 и закрытых предшественников, сохраняя исходный program240с/whole-chain210с. Отдельно проверяется текущий домен4c до port/tool каждого actor. Каждый этап требует собственного review/finiteGo; нового аппаратного кода, adapter, RS/ESC/US/cleanup/ROM/Flash/DATE пока не исполнялось. Возврат a053/данных/SD/часов ещё предстоит; `pow`/M4 без изменений.

## Полный фактический NEXT505 и первый этап возврата

Свежий последний Go002 `abbb2785…` исполнен один раз (старый Go001 не запускался). Все56 APP/COMPLETE449..504 завершились PASS:56 входов, собственных ошибок0/Qfplib0,56 пригодных групп быстрее без пересечения нуля. Старые1919 ledger точны, всего2031. Последний after-state `1b414c08…`, FLOW504 `63af2e02…`; POSTEXIT `fbeb05ae…`, RESULT `bd744475…`, ACTUAL-EXIT `61443fcd…`. Supervisor31309/actor+group31318 known0/reaped/gone/resourcePASS/ESRCH. Root независимо принял последний сегмент (`ac089650…`). Больше APP не запускалось.

Полный аппаратный итог NEXT:505 пакетов,22065 проверок, собственных ошибок0. У Qfplib/явных эталонных композиций1827 расхождений с точным ответом с учётом фокусных повторов. В464 группах ответы эталона правильны:427 медиан быстрее,37 медленнее.41 диагностическая группа сохранена отдельно. Эмпирические диапазоны разности пересекают ноль в46 (`f2d`),169/171 (`exp`) и307 (`dsub`); это не доверительные интервалы. Публичных вызовов обеих библиотек50318716, контрольных23301912. Этот конечный набор не доказывает корректность на всех binary64-входах.

| Остаточное отставание | Медианных проигрышей / пригодных групп | Неопределённые проигрыши |
|---|---:|---|
|sin|17 /34|нет|
|cos|14 /26|нет|
|exp|4 /7|169,171|
|atan|2 /4|нет|

В остальных пригодных группах медианы ниже Qfplib, с неопределённостью46/307. Все78 медианных ухудшений относительно собственной BASE, неверные эталоны, raw/control/cache и формулы композиций сохранены; BASE144 по-прежнему исключена и имеет NEXT/BASE=null. Версии запускались раздельно.

Исследовательские артефакты `.build/m0-nonpow-next505-actual-20261031-001`: RAW-SUMMARY1059162B/`03a10f35…`, ROLE-MANIFEST175296B/`97d40820…`, ROLE-VERIFICATION547646B/`44f80244…`, HARDWARE-SUMMARY.md3924B/`ffbe8b18…`. Неизменённый purebridge04b подтвердил на реальных данных477 нормальных результатов из9 actual PASS сегментов плюс28 явных partialHOLD004..031; все505 raw заново decoded,2031 ledger/4c/adapters точны, device/native/math/build/old-suite/write0. Старый HOLD2faf остался HOLD.

Root независимо собрал и принял собственный authoritative manifest175451B/`04811df2…`; ROOT-PICO-ACTUAL-NEXT505-ROLE-ACCEPTANCE-001.json2760B/`8c34b51d…`. Последующие actual grants используют этот authoritative manifest. Исследовательский manifest, уже созданный до Root-сообщения, сохранён без подмены истории. Finalization HOST source-пакет принят Root (`85ae54d8…`) отдельно от аппаратного допуска.

Отдельный Go первого этапа close-viewer `92b00ea7…` исполнен один раз PASS. Свежие UID/C5/RX/invariants подтвердились, RS1/ESC2 дали VIEWER→BROWSER→CLOSED; qualifiedUS1 вернул COMMAND. Typed-регистры/стек/программа/IP/будильники/настройки/epoch/UID/physical и домен4c совпали с final504/оригиналом. TX66/RX55504,8 ordinary commands; !/physical/APP/math/SDmutation/Flash/DATE0. Новый once OWN-VIEWER-CLOSE-FINAL-0011566B/`2d08f59d…`; прежние2031 ledger точны, теперь2032. Supervisor35136/actor+group35139 known0/reaped/gone/resourcePASS/ESRCH.

В `.build/m0-nonpow-finalize-20261031-001/outputs/close-viewer-001`: POSTEXIT556436B/`f9e547be…`, RESULT2902B/`1a2a5286…`, AUDIT2479B/`7bd9d2b1…`, current-state2636B/`cc4901b3…`; ACTUAL-EXIT2332B/`16941177…` в supervisor-outputs. Текущее состояние CLOSED/source0/COMMAND, epoch25/00010001,RTC_SET0,physical0,settings331. Это пока только выход и typed checkpoint; ownSDcleanup, ROM/full original Flash return и исходная траектория часов4c ещё предстоят по отдельным этапам. `pow` и M4 не менялись.

## Удаление собственной временной SD-нагрузки

Отдельный Root Go cleanup001 `4812dcff…` исполнен один раз PASS. Исходная процедура проверила побайтно TIMING.APP/INPUT504/RESULT504, затем удалила ровно RESULT.bin,INPUT.bin,TIMING.APP и собственный каталог `/MK61S-M0-TIMING-NONPOW-20261030`. Возвращённый список35 элементов корня в точности совпал с исходным по именам/типам/размерам. Содержимое каждого пользовательского файла отдельно не перечитывалось; операций записи в них не было. Рекурсивного удаления нет.

Entry typed capture2636B/`d691b92e…` совпал с принятой close-statecc490 по данным/настройкам/epoch/UID/physical и домену4c. Это исходное чтение cleanup до удаления; дополнительного полного typed-чтения после удаления не заявляется. Финальный C5 сохранил CLOSED/source0/COMMAND,epoch25/00010001,RTC_SET0,physical0,settings331.

TX492/RX63569,19 ordinary commands,US2;RS/ESC/!/APP/math/physical/Flash/DATE0. Supervisor37855/actor+group37861 known0/reaped/gone/resourcePASS/ESRCH. Новый SD-CLEANUP once1308B/`aa1be587…`; старые2032 ledger точны, теперь2033. В `outputs/cleanup-001`: POSTEXIT559146B/`a489c7b1…`, RESULT3920B/`827cffe5…`, AUDIT1834B/`34892cf4…`; ACTUAL-EXIT2302B/`ac094b20…` в supervisor-outputs. Досье передано Root, порт закрыт. OwnSD cleanup завершён; исходные a053 Flash и траектория RTC1/4c ещё не возвращены. Новых замеров/сборок/изменений `pow`/M4 нет.

## Финальный вход ROM для возврата оригинала

Root независимо принял cleanup (`36e6a737…`,2083refs). Отдельный Go ROM001 `66dfb6ba…` исполнен один раз PASS. Свежий typed capture `d8f0318a…` подтвердил неизменность данных/настроек/epoch/UID/physical и домена4c после удаления собственных файлов. Retained crash — прежний sequence2/flags25/already persisted;513B body`436e0717…` после нормализации CURRENT_BUILD совпал с исходным. Новой аварии, очистки crash или его перезаписи не заявляется.

Только qualifiedUS1/RS1/RAW!1,TX65/RX49187; полный ACK `Entering RP2040 USB BOOTSEL` и native errno6 disconnect. Flash/DATE/APP/math/SDmutation/physical/ESC0, picotool не запускался, ROM UID ещё не подтверждался инструментом. Supervisor38398/actor+group38403 known0/reaped/gone/resourcePASS/ESRCH. Новая once ROM-original895B/`87b46b51…`; старые2033 ledger точны, теперь2034. `outputs/rom-001`: POSTEXIT556774B/`6a5019b7…`, RESULT2091B/`dd67a1d8…`, AUDIT2509B/`9fb0e804…`; ACTUAL-EXIT2291B/`1f58301e…` в supervisor-outputs. Досье передано Root; дальнейшего I/O нет. Устройство передано в ROM, но исходная Flash a053 и часы ещё не возвращены; нужны отдельные freshROM metadata/restore/clock/verification этапы.

## Полное восстановление исходной Flash

Root принял ROM (`a557878f…`). Новый restore Go002 `48ea2c0a…` исполнен один раз PASS. Старый restore grant001 был отклонён Root в чистом HOST до actor/Go из-за отсутствующего tool_sha256, не исполнялся и сохранён. Fresh picotool подтвердил UID E6657CD423721C35/RP2040/2МиБ; before-full2MiB точно NEXTc9ac. Одна запись originala053, полное чтение обратно побайтно совпало с исходными2097152B, включая хвост настроек8192B; выполнен один штатный reboot. Это подтверждённый возврат Flash и boot request, но ещё не наблюдение postboot epoch/RTC.

Supervisor39179/actor+group39180 и пять tool PID39182,39185,39196,39243,39257 known0/reaped/gone/resourcePASS/ESRCH; signals/withdrawal/orphan/grace0. Whole-chain210с зарезервированы; перед единственным atomic load осталось231,575с, политика/argv/owner и tail170с исходные. Новая PROGRAM-original1188B/`22fde4ab…`; все старые2034 ledger точны, теперь2035. CDC/DATE/SD/APP/math/physical0. `outputs/restore-001`: POSTEXIT556541B/`de3bed9a…`, RESULT1592B/`3cb97e7e…`, AUDIT6328B/`4fcfa00f…`, ATOMIC-LOAD-ADMISSION1134B/`5422fe93…`; ACTUAL-EXIT2304B/`b29e909a…` в supervisor-outputs. Root получает actual dossier до дальнейших действий.

По запросу Root выполнен только HOST-разбор expected_return_boots/reset_reason: `host-receipts/POSTRESTORE-BOOT-METADATA-SOURCE-ANALYSIS-001.json`5323B/`9a5c8b66…`. diagnostics.cpp D6/NEXT совпадают побайтно (`e1e9abda…`): boots хранится в SRAM .uninitialized_data и увеличивается только при валидных magic/inverse, иначе становится1; reset_reason читается из watchdog.reason и chip_reset. Picotool для нормального RP2040 reboot отправляет PC_REBOOT(PC0,SP0,delay500). Значения26/00010001 — только условные кандидаты, не наблюдённый postboot epoch и не доказанные безусловные константы: положение/сохранность SRAM retained между образами/ROM/tool и итоговые reset-регистры этим Flash readback не подтверждаются. Дополнительных CDC/C5/DATE не было; Root предложен отдельный read-only admission перед единственной clock-return фазой.

Исходная Flash a053 восстановлена. OwnSD cleanup выполнен. Postboot typed data и исходная траектория RTC1/4c ещё требуют отдельной приёмки/возврата часов. `pow`, M4, старые frozen/HOLD и результаты математики не менялись.

## Отдельный C5 admission после полного возврата

Root независимо принял полный original readback/boot request (`2b3e9a5d…`,3029B), явно оставив postboot epoch ненаблюдённым. По его запросу подготовлен отдельный HOST-only пакет `.build/m0-nonpow-postrestore-c5-20261031-001`, без изменения frozen finalizer/clock helpers. READY2623B/`dda83d3d…`, FROZEN9958B/`bc8d1446…`, PREGO3498B/`0b26b9af…`; observe_original.py10659B/`11a7bec3…`.

Пакет переиспользует исходный одноразовый C5Only (`f9d26a73…`), original SET0/SET1 validate_frame, LiveLease/LeasePort/supervise/envelope. Границы30с/TX1/RX65536; ровно0x05, без обычных команд/US/RS/ESC/!/SD/APP/Flash/DATE/physical и без RTC-RETURN/DATE-once. Proof связывает actual original full return и новый Root normal OS/noholder snapshot после restore не старше120с. Actual epoch/reset/RTC читаются, не подставляются26/00010001. Сохраняются original D6FABB43/EFBF5584/CLOSED/source0/settings331/PPM0/crash enum/IP0/Xzero/physical0; полного typed recapture/UID getter этот этап не заявляет.

Все65 targeted HOST controls прошли: реальный неизменённый one-C5 writer и обе original validators, private enabled/disabled LiveLease без actor, проверка actual full-return refs, неправильные scope/budgets/состояния/поток/старые OS и уже потреблённая private RTC-RETURN. Review/OS positives явно HOST fixtures. Audit запретил процессы/device/native-clock и записи вне qualification output; все2035 существующих ledger и origin4c точны. REPORT17114B/`aee15fcf…`. Первоначальный чрезмерный audit запретил стандартный Python import ctypes.dlopen(None); это был только HOST import, аппаратных эффектов не было. Конечный harness допускает None import и запрещает настоящие native libraries.

Disabled template не активирован, hardware I/O0; новый finite Go и fresh OS metadata ещё требуются от координатора. Часы остаются pending, math/`pow`/M4/SDK/APP не менялись.

## Фактическое postrestore C5-наблюдение

Root независимо проверил31 refs/1418759B и все65 targeted HOST controls; source review2406B/`3e14748c…`. Выдан отдельный Go0022591B/`a20d343f…`, grant0025246B/`b77c3a3c…`; прежний grant001 отозван Root до Go/actor/I/O после преждевременного actor-only envelope check без будущего parentbudget. Go002 исполнен один раз, functions cell g13:570/chunk506d45/exit0.

Реальное наблюдение исходной прошивки: epoch26/00010001,RTC_SET0,COMMAND/SLEEP1,physical0,settings331/PPM0,original D6FABB43/EFBF5584/CLOSED/source0/IP0/Xzero и сохранённый crashenum AVAILABLE. Ровно TX1=05/RX3249; US/RS/ESC/!/ordinarycommands/SD/APP/Flash/DATE/physical0, RTC-RETURN не создавалась. Полного typed recapture и freshUIDgetter этап не заявляет. Supervisor44199/actor+group44200 known0/reaped/gone/resourcePASS/ESRCH,signals/withdrawal/orphan/grace0. Все2035 ledger/origin4c и31 frozenrefs точны.

Файлы `outputs/original-c5-001`: RESULT2199B/`57edab7d…`, C5-original.raw3249B/`89d702ed…`, POSTEXIT821694B/`12cb90df…`, OFFLINE-AUDIT1658B/`d3e44a24…`; ACTUAL-EXIT2288B/`93dab912…` в supervisor-outputs. Root переданы raw/известный exit и отдельное раскрытие timing: HOST pre-request проверка must_start_before прошла, но actual PARENT-BUDGET file time1793426770,942193 оказался25,92974с позже Go entry deadline1793426745,012453. Source runtime при этом прошёл freshOS≤120с, LiveLease expiry и30сbudget, finish1793426771,109778. История и границы не переименованы; решение по entry timing/actual acceptance остаётся Root. Повторов/дальнейшегоI/O нет. Original RTC1/4c и финальная typed verification ещё pending.

## Возврат исходной траектории часов

Root независимо проверил C5 raw/процессы и сохранил нарушение entry на25,92974с как FAIL, без заднего объявления своевременного Go. `ROOT-PICO-ORIGINAL-C5-ACTUAL-METADATA-CLOSE-001.json`2493B/`861ce6ca…` принимает честные наблюдённые метаданные только как источник для новой отдельно разрешённой проверки; старый canonical закрыт, повторного C5 не было.

Отдельный clockGo0013876B/`fb536486…`, grant`3cbdbcb1…` исполнен один раз PASS. Реальный parentbudget создан1793427723,5129218 до entrydeadline1793427988,804042; session120с, finish1793427724,52056. Qualified original clock selector повторно проверил actualepoch26/00010001. Полные typed data/settings/UI до SET0 и после SET1 точны; RTC_SET1/PPM0, исходная траектория4c прошла проверку без замены origin. Одна native DATE25B: request2026-10-31 09:22:06, observed09:22:07, fullsetterlatency7619875ns. Общий TX150/RX93723,28C5/US3/16ordinaryCLI плюс одна отдельная nativeDATE; RS/ESC/!/APP/SD/Flash/physical/reboot0.

Supervisor46841/actor+group46842 known0/reaped/gone/resourcePASS/ESRCH,signals/withdrawal/orphan/grace0. Старые2035 ledger точны, добавлена только RTC-RETURN867B/`6304f906…`, всего2036; original4c и178 frozenFrefs точны. `outputs/clock-001`: RESULT4799B/`2b648c49…`, current-state3593B/`cbc18d5d…`, POSTEXIT830046B/`5e25b02f…`, OFFLINE-AUDIT1613B/`446f54f9…`, NATIVE-DATE-RECEIPT468B/`659f5185…`; ACTUAL-EXIT2315B/`6d1db4a2…` в supervisor-outputs. Functions exec6ed91a/session83742/completionb34e5f/exit0. В подготовке offline seal исправлены только предположения о list-формате FROZEN и отдельном счётчике nativeDATE; источник/runtime/грант/результаты не менялись, до окончательного seal POSTEXIT не создавался.

Часы и typed data возвращены на этом этапе. Досье передано Root; остаётся его независимая приёмка и отдельная finalverify без записи. Git/main/BBS/Ms/`pow`/M4 не менялись.

## Финальная проверка возврата без записи

Root независимо принял clock (`ROOT-PICO-FINAL-CLOCK-ACTUAL-CLOSE-001.json`2394B/`043d39dd…`): typed/data/4c,28actualC5/однаDATE/2035старыхledger+единственныйRTC-RETURN/timelyentry/PIDgroups. Старый verify grant001 отклонён Root до Go/actor/I/O из-за исторической SET0 current_state, отозван и сохранён.

Новый Go0023878B/`639994b0…`, grant`20d609e3…` исполнен один раз PASS, chunk1ed07c/exit0. Parentbudget1793429199,0292358 доentrydeadline1793429458,8896818,finish1793429199,660437. Original final return stage подтвердил исходные typed/currentdata/settings/UI,RTC_SET1/PPM0/epoch26/00010001/physical0 и4c trajectoryPASS. Календарь2026-10-31 09:46:42. TX49/RX36707,11C5/US1/7fixedgetters(identity/reg/stk/hout/pwd/alarm/dateget); RS/ESC/!/DATEsetter/APP/SD/Flash/physical/reboot0. Новых once claims нет, все2036 ledger и178 frozenFrefs точны.

Supervisor54611/actor+group54612 known0/reaped/gone/resourcePASS/ESRCH,signals/withdrawal/orphan/grace0; свой порт закрыт, глобальный noholder не заявляется. `outputs/verify-001`: RESULT1582B/`fb80729f…`, current-state2634B/`27b60366…`, POSTEXIT825214B/`d0c2a27c…`, OFFLINE-AUDIT1308B/`73a211e8…`; ACTUAL-EXIT2308B/`652f8658…` в supervisor-outputs. Actual досье передано Root для независимой итоговой приёмки. Исходная Flash a053, ownSDcleanup, typed data и исходная RTC1-траектория возвращены и проверены; все аппаратные этапы завершены, дальнейшегоI/O нет. Матрица505/BASE144exclusion/старыеHOLD и C5entryFAIL сохранены. `pow`/M4/Git/main/BBS/Ms не менялись.

## Независимая итоговая приёмка координатора

Root независимо принял финальный возврат: ROOT-PICO-FINAL-VERIFY-ACTUAL-CLOSE-001.json3468B/SHA85ba1b593f5e6f0ce5ecba61efa7568d5a443fd1b3f9a4fc97cc2f8c58d4c488. Подтверждены исходные typed data/settings/UI,4c trajectory/RTC1/PPM0,11C5/7getters/US1, все2036 ledger, своевременный entry и PID/PG ESRCH. Canonical закрыт/consumed; все hardware-фазы закончены. OriginalFlash/ownSDcleanup/data/clock возвращены; ранний C5 entryFAIL сохранён. Дополнительного I/O нет. Готовая математика выделяется в отдельной ветке от main для передачи единственному интегратору; приватные Flash/SD в Git не включаются.
