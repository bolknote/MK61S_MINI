"""Summarize local ablations and derive a concrete next-training proposal."""
import collections
import json
from ad_common import ROOT,HERE,MODEL,PREVIOUS,read,write,sha
from ad_experiment import public_task,grade
from full_isa_vm import FullVM
from ha_protocol import assemble,constants

NAMES={'greedy_raw':'Обычная генерация','greedy_guard':'Проверка запусков перед DONE',
    'best4_likelihood':'4 кандидата, оценка сети','best4_statistics':'Выбранная статистика (вес 0)',
    'nonzero_statistics':'4 кандидата, статистика (вес 0.25)','best4_feedback':'4 кандидата + замечания критика'}


def brief(t):return {k:v for k,v in t.items()if k not in ['details','actions']}


def main():
    assert json.loads((ROOT/'verification.json').read_text())['complete']
    assert(ROOT/'diversity-development.json').exists()
    selection=json.loads((ROOT/'selection.json').read_text());diversity=json.loads((ROOT/'diversity-development.json').read_text())
    candidate=json.loads((ROOT/'exam-candidate-summary.json').read_text());nonzero=json.loads((ROOT/'nonzero-exam-candidate-summary.json').read_text())
    bank=json.loads((ROOT/'exam-candidate-panel.json').read_text());frozen=json.loads((ROOT/'data-frozen.json').read_text());verification=json.loads((ROOT/'verification.json').read_text())
    arms={a:json.loads((ROOT/(a+'-exam.json')).read_text())for a in NAMES}
    rows=bank['details'];uniqueness=collections.Counter(len({tuple(c['generation']['body'])for c in r['candidates']if not c['generation'].get('codec_error')})for r in rows)
    bottleneck={}
    for level in [1,2]:
        part=[r for r in rows if r['level']==level and not r['initially_correct']]
        bottleneck[level]={'total':len(part),'greedy_correct':sum(r['candidates'][0]['correct_offline']for r in part),
             'any_correct_4':sum(any(c['correct_offline']for c in r['candidates'])for r in part)}
    following=collections.Counter()
    for r in arms['best4_feedback']['main']['details']:
        for at,h in enumerate(r['history']):
            if h['kind']=='critic_rejected_DONE':following[r['history'][at+1]['kind']if at+1<len(r['history'])else'budget_exhausted']+=1
    # Check explicit formatting contracts separately; frozen main scores are not relabelled.
    tasks={t['id']:t for t in read(ROOT/'exam.jsonl')};vm=FullVM();contract={}
    for arm,result in arms.items():
        missing=[]
        for r in result['main']['details']:
            t=tasks[r['id']]
            if not r['pass']or t['group']!='algorithm_subroutine':continue
            code=assemble(r['body'],t.get('constants')or constants(t['task']),'asm')
            actual,_=vm.execute(code,t['public_tests'][0]['segments'][0]['inputs'],angle=t['angle'],max_commands=128,max_frames=1024)
            opcodes={e['opcode']for e in actual['trace']}
            if not{0x53,0x52}<=opcodes:missing.append(r['id'])
        contract[arm]={'numeric_successes_missing_executed_call_and_return':len(missing),'ids':missing}
    def check_public(obj):
        if isinstance(obj,dict):
            assert not({'reference_code','hidden_tests','expected'}&set(obj))
            for value in obj.values():check_public(value)
        elif isinstance(obj,list):
            for value in obj:check_public(value)
    for t in tasks.values():check_public(public_task(t))
    write(ROOT/'analysis.json',{'candidate_uniqueness':dict(uniqueness),'bottleneck_by_level':bottleneck,
        'after_critic_warning':dict(following),'explicit_subroutine_contract_audit':contract,'public_only_views_checked':len(tasks)})
    lines=['# Локальное моделирование статистического критика МК-61','',
       'Все прогоны выполнены на локальном компьютере. Использованы неизменённые реальные Q4-веса Flourish-3M, SFT block4. Вычисления в PyTorch FP32; арифметика программ — в настоящем ROM-эмуляторе. Нового SGD, SSH-запусков на B200 и установки в прошивку не было.','',
       'Данные зафиксированы до генерации: 64 задачи настройки (128 состояний) и 128 новых экзаменационных задач (256 состояний). В каждой паре одинаковы расписание запусков/трасс и ревизия, но исходный код правильный или ошибочный. Дополнительный экзамен: 64 состояния с разными целями при одинаковых программах/фактах и 32 задачи с нуля, поровну простых и составных. Семейства частично знакомы; это новые экземпляры и формулировки, а не полностью новые классы алгоритмов.','',
       'На исходных состояниях сохранены общий жадный кандидат и три независимых сэмпла T=0.8, top_p=0.95. Поток случайных чисел закреплён за текстом запроса и номером кандидата; общие запросы используют один банк кандидатов. Дополнительные состояния разных траекторий генерируются по мере необходимости и также кешируются. Контроллер выбирает действия сам. Дополнительные кандидаты в полном цикле создаются только при выбранном WRITE.','',
       'Проверка DONE в защищённых вариантах требует запуска и останова всех публичных случаев на текущей версии. Она не проверяет смысл результата. Статистический критик получает только код и явную таблицу констант, без эталона и скрытых тестов. Оценки истинной правильности доступны исключительно офлайн-проверяющему.','',
       'Критик учитывает среднее логарифмическое правдоподобие троек нормализованных команд, соседние повторяющиеся блоки и консервативную достижимость при первом запуске. Параметры переходов пропускаются, числа и номера регистров обобщаются. При косвенных переходах/перекрытии кода анализ достижимости воздерживается. Вызванная подпрограмма после первого С/П считается достижимой. Продолжение после С/П не объявляется автоматически ошибкой.','',
       f'Сетка выбиралась только на настройке: лучший вариант **{selection["config"]}**. При равенстве результатов предпочиталось меньше вмешательств. Отдельно зафиксирован лучший вариант с ненулевым весом 0.25, выбранный также без экзаменационных метрик. На настройке оба дают 72/128 правильных кандидата.','',
       '| Полный цикл, основной экзамен | Численные проверки + покрытие /256 | Исправлено /128 | Правильных стартов сохранено /128 | Ложных DONE по вычислению | UNSURE | Доп. генераций | Выходных токенов |',
       '|---|---:|---:|---:|---:|---:|---:|---:|']
    for arm,result in arms.items():
        t=result['main'];lines.append(f'| {NAMES[arm]} | {t["passed"]} | {t["repaired"]} | {t["correct_controls_completed"]} | {t["false_DONE"]} | {t["abstained"]} | {t["candidate_generations"]} | {t["logical_output_tokens"]:,} |')
    lines+=['','Зафиксированный до эксперимента основной критерий: программа проходит публичные и скрытые численные/регистровые проверки, модель объявила DONE и выполнила все публичные случаи на последней версии. UNSURE и исчерпанный бюджет — нерешённые. Проверки не доказывают правильность на всех возможных входах. Число выходных токенов — счётчик выбранных/отброшенных генераций; он не включает все расходы префилла и расчёта likelihood. Время прохода конкретного варианта нельзя сравнивать напрямую из-за общего кеша.','',
       'Дополнительный аудит явного требования подпрограммы выполнен после основных прогонов. Он не меняет сохранённые исходные оценки: ниже отдельно учтено наличие реально выполненных ПП и В/О в задании, где пользователь этого требует. Единственный дополнительный численный успех перебора нарушил это условие.','',
       '| Вариант | Прошёл все проверенные условия /256 | Численно успешных, но без требуемой подпрограммы |','|---|---:|---:|']
    for arm,result in arms.items():
        miss=contract[arm]['numeric_successes_missing_executed_call_and_return']
        lines.append(f'| {NAMES[arm]} | {result["main"]["passed"]-miss} | {miss} |')
    lines+=['',
       '| Дополнительный экзамен | Цели с одинаковыми фактами /64 | С нуля /32 | Ложных DONE с нуля |','|---|---:|---:|---:|']
    for arm,result in arms.items():lines.append(f'| {NAMES[arm]} | {result["goal_twins"]["passed"]} | {result["from_scratch"]["passed"]} | {result["from_scratch"]["false_DONE"]} |')
    lines+=['','Отдельная диагностика выбора первого исправления, все 256 исходных состояний (WRITE принудительно запрашивается и у выбравших другое действие):','',
       f'- Первый кандидат правильный: {candidate["greedy"]["passed"]}/256.',
       f'- Выбор по оценке сети с отбраковкой несобираемого: {candidate["likelihood"]["passed"]}/256.',
       f'- Ненулевой статистический вес 0.25: {nonzero["statistics"]["passed"]}/256.',
       f'- Если офлайн-оракул выбрал бы любой правильный из четырёх: {candidate["oracle_best_of_4"]["passed"]}/256. В рабочем алгоритме оракул не используется.',
       f'- В {uniqueness[1]}/256 состояниях четыре кандидата совпадают. В {candidate["wrong_start_bottleneck"]["no_correct_candidate_among_4"]}/128 ошибочных стартах правильного среди четырёх нет.',
       f'- Среди ошибочных стартов простые задачи: правильный первый кандидат {bottleneck[1]["greedy_correct"]}/64, любой из четырёх {bottleneck[1]["any_correct_4"]}/64. Составные: {bottleneck[2]["greedy_correct"]}/64 и {bottleneck[2]["any_correct_4"]}/64.',
       f'- В {candidate["wrong_start_bottleneck"]["policy_DONE_but_correct_candidate_exists"]} состояниях модель сразу выбирает DONE, хотя среди принудительно запрошенных программ есть верная.','',
       f'Диагностика разнообразия выполнялась только на настройке: 64 ошибочных старта. Жадный код правильный в {diversity["greedy_correct"]}; среди 4 кандидатов верный есть в {diversity["oracle_4"]}, среди 16 (12 дополнительных при T=1.1/top_p=0.98) — в {diversity["oracle_16"]}. Это показывает возможности более широкого поиска, но не доступный рабочему алгоритму способ выбрать верный код. Для нового режима не заявляется независимый экзаменационный результат.','',
       'Выводы из моделирования:','',
       '- На этом наборе статистический приоритет не дал улучшения полного решения. Ненулевой вес меняет некоторые решения, но после дополнительной проверки подпрограммы остаётся 141/256, как у исходного варианта.',
       '- Перебор увеличил выходной поток примерно втрое с половиной. Единственный дополнительный численный успех не выполнил требование подпрограммы, поэтому полного выигрыша нет.',
       '- Замечания критика уменьшают ложные завершения, но снижают число сохранённых правильных программ. Это не равнозначно улучшению отладки.',
       f'- На {verification["retention_reference_programs"]} корректных тестовых обвязках документированных команд критик выдал {verification["retention_reference_warnings"]} предупреждений. Эти обвязки отличаются от обычных арифметических программ; порог, настроенный на формулах, и признак повторов туда не переносятся. Делать из предупреждения жёсткий запрет нельзя.',
       f'- После замечания при DONE следующие действия: {dict(following)}. Модель часто переписывает программу; часть таких переписываний портит правильный код.',
       '- Большой остаток ошибок связан с содержанием программы и соответствием условию. Пары/тройки команд не различают неправильную константу, регистр или правдоподобную неверную операцию.','',
       'План следующего обучения, предлагаемый по этим результатам:','',
       '1. Развести обучение составлению кода и решению о завершении. Добавить отдельную вспомогательную задачу «текущая программа соответствует условию» и прямые контрасты DONE/WRITE/UNSURE на одинаковом состоянии. Дать особенно большой вес ложным подтверждениям, одновременно контролируя сохранение правильных решений. Эта головка оценивает соответствие цели, а покрытие публичных запусков остаётся отдельной строгой проверкой. Две строки можно разместить в свободных служебных выходных строках, которые не подаются на вход: русский словарь и число параметров сохраняются. Такая оценка сама остаётся обучаемой, а не доказательством правильности. Финальный критерий нулевых ложных DONE сохраняется; он не является условием допуска к изучению новых операций.',
       '2. Учить двух- и трёхоператорным композициям из уже освоенных операций параллельно с одиночными. Старый общий порог продвижения оставил обе модели на первой ступени, поэтому сложные отладки фактически не обучались. Нужен отдельный график сложности по освоенным операциям, а не ожидание идеального DONE на всём простом наборе.',
       '3. Отдельный курс привязки аргументов: 0/1/−1/22, знак и десятичные числа, номера регистров, режим углов. В части офлайн-эпизодов переставлять явную таблицу констант и согласованно перекодировать все ссылки. Фактический машинный код должен оставаться тем же; это учит читать таблицу вместо запоминания привычного индекса. Перестановки имён регистров также проверять исполнением.',
       '4. Сбор собственных состояний уже был в предыдущем обучении. Его следует расширить проверенными альтернативными программами и разметкой причины несоответствия цели: операция, константа, регистр, управление, дополнительные требования. Для случаев, где ученик находит правильный вариант при расширенном поиске, использовать проверенные варианты для SFT/дистилляции. Для остальных получать исправление от сильного учителя и проверять в ROM-эмуляторе. Учитель должен решать задачу, а не только исправлять формат. Новые учебные экземпляры генерировать отдельно от этого экзамена.',
       '5. Обучать реакции на критика попарно: нетипичный, но правильный код нужно сохранить; правдоподобный, но неверный — исправить. Статистический балл не используется как награда за истинную правильность. Корректность, успешный запуск и похожесть на корпус — разные метки.',
       '6. Сравнить ёмкость обучения инструментального профиля: текущий Q/V rank4, более ёмкий rank16 с MLP-адаптерами, полный transformer-профиль с защищёнными русскими входными embedding-строками. Исходный компилятор остаётся отдельным неизменённым файлом. Слияние адаптеров либо полное обучение существующих матриц не увеличивает число исполняемых параметров: каждый профиль остаётся 3 022 080 параметров Q4. Увеличение ранга не гарантирует улучшения — нужна одинаковая выборка и контроль по Q4.',
       '7. Явно размечать дополнительные требования, например реально выполненные ПП/В/О, если пользователь требует подпрограмму. Численный результат сам по себе не проверяет все такие требования. Дополнительный разбор уже записанных успехов по этому требованию приведён в analysis.json; исходные метрики не переименованы задним числом.','',
       'Следующий контролируемый прогон разумно начать с SFT на таком курсе и сравнения ёмкости инструментального профиля. В предыдущем парном опыте DPO полных траекторий не обошёл SFT, поэтому его повторение на тех же данных не выбрано главным направлением.','',
       'Научные основания отдельных частей плана: [DAgger — обучение на состояниях ученика](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf), [CodeRL — использование результатов выполнения при обучении коду](https://arxiv.org/abs/2207.01780), [LoRA — обучаемые поправки к замороженным матрицам и слияние](https://arxiv.org/abs/2106.09685). Эти работы не доказывают достижимость надёжной отладки для нашей 3M; предложенные изменения являются проверяемыми гипотезами.','',
       'Локальный CLI: `.build/squeal-chat-20261105/venv/bin/python research/mk61-agent-20261106/ad_chat.py --angle DEG --mode greedy_guard "Подсчитай синус 22."`. Режимы: greedy_guard, best4_likelihood, nonzero_statistics, feedback. `--initial-hex` задаёт обычные машинные байты исходной программы; `--tests` — публичные входы JSON. Доверенного эталона у CLI нет, поэтому verified_task_success:null даже при DONE.','',
       'Артефакты: `.build/mk61-agent-20261106/stats-harness-v1`. Проверены хеши весов, корпуса, статистических таблиц и исходников ядра эксперимента; случайные потоки воспроизведены; отдельно проверена достижимость вызываемой подпрограммы. Все локальные задания завершены.']
    path=HERE/'LOCAL_STATISTICS_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    summary={'completed':True,'inference_only':True,'optimizer_updates':0,'report':str(path),'selected_config':selection['config'],
        'results':{a:{k:brief(v)for k,v in result.items()if isinstance(v,dict)and'passed'in v}for a,result in arms.items()},
        'candidate_panel':candidate,'candidate_panel_nonzero':nonzero,'development_diversity':{k:v for k,v in diversity.items()if k!='details'},
        'all_checked_requirements_main':{a:r['main']['passed']-contract[a]['numeric_successes_missing_executed_call_and_return']for a,r in arms.items()},
        'all_local_jobs_complete':True,'deployed_to_device':False}
    write(ROOT/'summary.json',summary)
    state_path=HERE/'work-state.json';state=json.loads(state_path.read_text());state.update(phase='local_stats_harness_complete',active_experiment=None,all_own_jobs_complete=True,
       next_action='Review local statistics results and proposed training changes; no new SGD or firmware deployment started.')
    state['local_statistics_simulation']={'completed':True,'report':str(path),'artifact_root':str(ROOT),'optimizer_updates':0};write(state_path,state)
    print(json.dumps({'completed':True,'report':str(path),'main':{a:result['main']['passed']for a,result in arms.items()}}),flush=True)


if __name__=='__main__':main()
