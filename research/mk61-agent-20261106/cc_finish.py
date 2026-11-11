"""Report completed Q4 decision training and account the actual head updates once."""
import time
import json
from cc_common import ROOT,HERE,read,write,rows,sha,check_frozen
from by_finish import analyze,transitions
from bl_spec import install
from bl_vm import CachedVM

def brief(s):return{k:s[k]for k in ['total','passed','correct_starts_completed','wrong_starts_repaired','false_DONE','correct_starts_corrupted','context_overflows','abstained']}

def main():
    check_frozen();install();vm=CachedVM();root=ROOT/'server-results'
    assert read(root/'controller-complete.json')['all_own_workers_joined']and read(root/'postflight.json')['Qwen_health']=='200'
    native=read(root/'native-verification.json');training=read(root/'training.json');selection=read(root/'preselected.json')
    assert native['complete']and not selection['closed_seen'];roles=read(root/'audit-roles.json');goals=rows(ROOT/'closed.jsonl')
    reports={r:read(root/f'closed-{r}.json')for r in roles['evaluated']};closed={r:analyze(v,goals,vm)for r,v in reports.items()}
    selected='selected'if roles['selected_step']else'parent';final='final'if'final'in reports else selected
    recommended='selected'if roles['selected_step']else'working'
    candidate=selected if roles['selected_step']else final
    pairs={'candidate_vs_parent':('parent',candidate),'candidate_vs_working':('working',candidate),
        'final_weights_vs_parent':('parent',final),'preselected_vs_parent':('parent',selected),'recommended_vs_working':('working',recommended)}
    comparisons={name:transitions(reports[a],reports[b],goals)for name,(a,b)in pairs.items()}
    development={r:{s:read(root/f'{r}-{s}.json')['own']['summary']for s in ['development','retention']}for r in ['working','parent','step-200','step-800']}
    retention={r:{x['id']:x for x in read(root/f'{r}-retention.json')['own']['records']}for r in development}
    decisions={};retention_changes={}
    for step in [200,800]:
        d=read(root/f'selection-{step}.json');decisions[str(step)]={'eligible':d['eligible'],'failed_checks':[k for k,v in d['checks'].items()if not v]}
        candidate_cases=retention[f'step-{step}'];retention_changes[str(step)]={}
        for role in ['parent','working']:
            reference=retention[role];assert reference.keys()==candidate_cases.keys()
            lost=[v for k,v in reference.items()if v['pass']and not candidate_cases[k]['pass']]
            retention_changes[str(step)][role]={'lost_repairs':[v['id']for v in lost if not v['initially_correct']],
                'lost_correct_finishes':[v['id']for v in lost if v['initially_correct']],
                'gained':[k for k,v in reference.items()if not v['pass']and candidate_cases[k]['pass']]}
    lesson_info=read(ROOT/'lessons-frozen.json')
    result={'complete':True,'optimizer_updates':training['optimizer_updates'],'trainable_parameters':384,'selected_step':roles['selected_step'],
        'recommended_runtime':recommended,'final_role':final,'headline_candidate_role':candidate,'closed_tasks':len(goals),'closed_used_for_selection':False,
        'body_weights_frozen_and_verified':True,'translator_unchanged':True,'closed':closed,'comparisons':comparisons,
        'development':development,'decisions':decisions,'retention_case_changes':retention_changes,'selection':selection,'native_streams':native['streams_verified'],
        'lesson_info':lesson_info,'frozen_translator_primary':reports['parent']['primary']['summary'],
        'closed_replan_transitions':{r:v['own']['replan']for r,v in reports.items()},
        'control_decision_diagnostics':read(ROOT/'control-decision-diagnostics.json')if(ROOT/'control-decision-diagnostics.json').exists()else None}
    write(ROOT/'comparison.json',result);p=closed['parent']['summary'];f=closed[candidate]['summary'];w=closed['working']['summary']
    lines=['# Дообучение выбора SPEC / WRITE / DONE','',
        f"Завершены {training['optimizer_updates']} обновлений 384 коэффициентов выбора WRITE/DONE/DIAG. На новом закрытом наборе Q4: родитель CB→кандидат {candidate} — завершения {p['passed']}→{f['passed']}, исправления {p['wrong_starts_repaired']}→{f['wrong_starts_repaired']}, принятые ложные DONE {p['false_DONE']}→{f['false_DONE']}, итоговая порча {p['correct_starts_corrupted']}→{f['correct_starts_corrupted']}. Выбор по development/retention зафиксирован до закрытого прогона: шаг {roles['selected_step']}, режим по этому критерию {recommended}. При шаге0 кандидат final показан только для исследовательского аудита. Прежний продуктовый профиль не заменён.",'',
        '## Что обучалось','',
        'Исходная точка — последние CB-веса с улучшенными исправлениями, отдельный контроль — прежний рабочий исполнитель. Менялись только три существующие строки выходного выбора действия, по128 коэффициентов. Кодировщик, остальные строки действий, генерация HEX/SPEC-тела и переводчик BU1500 заморожены. Новых параметров, токенов, полей запроса или разрешений упряжи нет. Используется полностью прежний формат без нового счётчика, окно1024, FP32 KV, бюджет12, прежние RUN00/01, проверка DONE и откат.','',
        'Q4 применяется на каждом проходе обучаемой головы. Скрытые признаки получены замороженным Q4-кодировщиком на B200 исключительно из учебных запросов; 384 коэффициента обучались на CPU FP32. Тело модели не получает градиентов. После экспорта остаются 3 022 080 параметров.','',
        '## Данные и критерии','',
        'Восемь полных четверок SPEC×код дают32 состояния на шаг. Дополнительно:16 пропущенных нужных пересмотров,16 состояний успешных исправлений,32 успешных повторов,16 завершений правильного кода,8 RUN,8 UNSURE — всего128. Обучение: gold action CE +2 KL только там, где правильное предсказание родителя подтверждено разметкой, +0.05 L2 к прежней голове. Штрафа за DONE и body CE нет.','',
        f"Получено {lesson_info['states']} состояний, {lesson_info['four_way_groups']} полных четверок; источник реальных траекторий — {lesson_info['onpolicy']['episodes']} прежних эпизодов. При одинаковом прежнем запросе не назначаются разные действия только из-за невидимого флага уже использованного пересмотра. Такие отрицательные состояния исключены; все оставшиеся конфликты меток для одинакового текста исключены целиком. Полные четверки имеют разные правильность SPEC и кода при одном условии и одном случае запуска. Метки проверены компилятором и эмулятором.",'',
        'Новые development64 и closed256 зафиксированы до обучения, с новыми числами и отложенными сочетаниями операций. Старые панели выведены из роли теста;48 старых успешных задач отложены для контроля сохранения и исключены из обучения. DeepSeek сформулировал условия и дважды восстановил смысл вслепую; это тот же учитель, а не независимая человеческая разметка.','',
        'Чекпойнты200/800 допускаются, если в development и retention завершения/исправления/доведённые правильные старты не ниже обоих контролей, принятые ложные DONE/порча/эпизоды ложных заявлений не выше обоих, все индивидуальные прежние успехи retention сохранены и есть улучшение относительно CB на development. При провале продуктовой рекомендацией остаётся working. Закрытый тест не меняет решение.','',
        '| Версия | Панель | Завершено | Исправлено | Правильный старт доведён | Принятые ложные DONE | Итоговая порча |',
        '|---|---|---:|---:|---:|---:|---:|']
    for role,panels in development.items():
        for split,s in panels.items():lines.append(f"| {role} | {split} | {s['passed']}/{s['total']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['false_DONE']} | {s['correct_starts_corrupted']} |")
    lines+=['','| Шаг | Относительно | Потерянные старые исправления | Потерянные завершения с правильным стартом | Новые успехи |',
        '|---|---|---:|---:|---:|']
    for step,controls in retention_changes.items():
        for role,t in controls.items():lines.append(f"| {step} | {role} | {len(t['lost_repairs'])} | {len(t['lost_correct_finishes'])} | {len(t['gained'])} |")
    if result['control_decision_diagnostics']:
        reviews=result['control_decision_diagnostics']['development']['replans']['step-800']
        lines+=['',f"На development шаг800 сделал {reviews['replanned']} пересмотров: неверную SPEC удалось исправить в {reviews['wrong_to_correct']} эпизодах, а верная стала неверной в {reviews['correct_to_wrong']}. Рост числа пересмотров сам по себе не является улучшением выбора."]
    lines+=['','## Новый закрытый тест в Q4','',
        '256 новых задач, в том числе160 композиций из32 новых семейств, по32 унарных, бинарных и чисто константных. На каждой задаче два старта: верный код и мутант; всего512 эпизодов. Во всех режимах агент получает собственную SPEC, без эталона. Начальные переводы токен в токен одинаковы у всех контролей.','',
        '| Версия | Завершено /512 | Исправлено /256 | Правильный старт доведён /256 | Принятые ложные DONE | Порча после отката | Переполнение | Отказ |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for role,v in closed.items():
        s=v['summary'];lines.append(f"| {role} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['false_DONE']} | {s['correct_starts_corrupted']} | {s['context_overflows']} | {s['abstained']} |")
    lines+=['','| Версия | Неверный WRITE при верном старте | Ложных заявлений DONE / всех | Пересмотров | Исправлений неверной SPEC | Порча верной SPEC пересмотром |',
        '|---|---:|---:|---:|---:|---:|']
    for role,v in closed.items():
        s=v['summary'];r=reports[role]['own']['replan'];lines.append(f"| {role} | {v['counts'].get('correct_start:with_wrong_WRITE',0)} | {s['false_DONE_claims']}/{s['all_DONE_claims']} | {s['replans']} | {r['wrong_to_correct']} | {r['correct_to_wrong']} |")
    lines+=['','Ложное заявление может быть отклонено упряжью; принятый ложный DONE — отдельная метрика. Проверка сравнивает программу с заявленной SPEC, поэтому неверное понимание условия всё ещё может дать принятый ложный ответ. Итоговая порча считается после отката; неверные WRITE до отката показаны отдельно. Неизменность генерации тела при выбранном действии не гарантирует неизменность траекторий.','',
        '## Парная неопределённость','',
        '95% интервалы по10 000 bootstrap-выборкам256 задач, оба старта одной задачи остаются вместе. Один прогон обучения, без доказательства предела ёмкости. Панель не охватывает произвольные циклы и ветвления МК-61.','',
        '| Сравнение | Завершения, п.п. [95%] | Исправления, п.п. [95%] | Принятые ложные DONE, п.п. [95%] | Порча, п.п. [95%] |',
        '|---|---:|---:|---:|---:|']
    for name,v in comparisons.items():
        cells=[]
        for key in ['completion','repairs','accepted_false_DONE','corruption']:
            q=v['paired_uncertainty'][key];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.2f} [{lo:+.2f}; {hi:+.2f}]")
        lines.append('| '+name+' | '+' | '.join(cells)+' |')
    lines+=['','## Проверка экспорта и ресурсы','',
        f"HF-мастера воспроизвели Q4 payload. Во всех {native['streams_verified']} выбранных генерациях токены совпали на B200/CPU/C++. Прямое сравнение тензоров подтверждает, что у обученных экспортов отличаются только разрешённые строки действий; проверок неизменности тела при принудительно одинаковом действии: {len(native['conditional_body_checks'])}.",'',
        f"Один буфер весов {native['one_weight_buffer_bytes']} байт, KV {native['KV_bytes']} байт, workspace {native['workspace_bytes']} байт. Размер модели не вырос. Физический PicoCalc не измерялся. Все собственные GPU-задачи завершены; Qwen отвечает200, его сервис не изменялся.",'',
        'Артефакты: `.build/mk61-agent-20261106/spec-action-choice-v1/comparison.json`, `server-results/training.json`, `server-results/preselected.json`, `server-results/native-verification.json`.','']
    report=HERE/'ACTION_CHOICE_TRAINING_RESULTS.md';report.write_text('\n'.join(lines))
    state=read(HERE/'work-state.json');entry=state.get('latest_action_choice_training',{})
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=1;state['total_accounted_optimizer_updates_lower_bound']+=training['optimizer_updates']
    entry.update(phase='complete',complete=True,optimizer_updates=training['optimizer_updates'],ledger_accounted=True,selected_step=roles['selected_step'],
        report=str(report),native_streams=native['streams_verified'],closed={r:brief(v['summary'])for r,v in closed.items()})
    state.update(latest_action_choice_training=entry,active_experiment=None,all_own_jobs_complete=True,phase='action_choice_training_complete',
        next_action='Interpret action-selection gains separately from the frozen body; retain the preselected recommendation and use fresh tasks for further training decisions.')
    write(HERE/'work-state.json',state);write(ROOT/'finish.json',{'complete':True,'optimizer_updates':training['optimizer_updates'],'ledger_accounted':True,
        'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print(json.dumps({'complete':True,'report':str(report),'selected_step':roles['selected_step'],'recommended_runtime':recommended,
        'updates':training['optimizer_updates'],'closed':entry['closed'],'native_streams':native['streams_verified'],
        'ledger_runs':state['completed_training_runs'],'ledger_updates':state['total_accounted_optimizer_updates_lower_bound']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
