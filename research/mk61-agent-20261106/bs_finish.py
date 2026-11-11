"""Report the complete course, including failed preservation gates and false claims."""
import json
import collections
import time
import numpy as np
from bs_common import ROOT,HERE,read,write,sha,check_frozen
from br_finish import paired


def main(root):
    check_frozen();assert read(root/'controller-complete.json')['all_own_workers_joined'];native=read(root/'native-verification.json');assert native['complete']
    training=read(root/'training.json');assert training['optimizer_updates']==read(ROOT/'policy.json')['steps']
    selection=read(root/'preselected.json')['chosen'];roles=['parent_compact','parent_long','selected','final'];reports={a:read(root/('closed-'+a+'.json'))for a in roles}
    uncertainty={role:{a:paired(reports[a]['own']['records'],reports[role]['own']['records'])for a in ['parent_compact','parent_long']}
                 for role in ['selected','final']}
    data=read(ROOT/'data-frozen.json');report=HERE/'DIVERSE_SPEC_RECOVERY_RESULTS.md'
    conclusion=('Ни один новый чекпойнт не прошёл защитные критерии; выбранным остаётся прежний рабочий родитель. Результат дообучения не принят как улучшение.'if selection['step']==0 else
                'Новый чекпойнт прошёл защитные критерии на development; его перенос оценивается ниже на новом закрытом наборе.')
    old=reports['parent_compact'];working=reports['parent_long'];new=reports['final']
    lines=['# Разнообразные циклы SPEC с сохранением прежнего перевода','',conclusion,'',
       f"Главный результат: в одинаковом компактном протоколе завершения упали {old['own']['summary']['passed']}→{new['own']['summary']['passed']} из 512, а принятые ложные DONE выросли {old['own']['summary']['false_DONE']}→{new['own']['summary']['false_DONE']}. Прежний длинный профиль завершает {working['own']['summary']['passed']}/512. Улучшение направленного восстановления не перенеслось на самостоятельный цикл.",'',
       f"При правильной SPEC, заданной проверяющим, восстановление после отклонённого DONE улучшилось: исправления {old['recovery']['summary']['wrong_starts_repaired']}→{new['recovery']['summary']['wrong_starts_repaired']} из 64, доведение уже верного кода {old['recovery']['summary']['correct_starts_completed']}→{new['recovery']['summary']['correct_starts_completed']} из 64. Первоначальный перевод условий изменился лишь {old['primary']['summary']['passed']}→{new['primary']['summary']['passed']} из 256. Положительный результат относится к явно направленному инструментальному протоколу, а не к общей автономности.",'',
       f"Обучение завершено: {training['optimizer_updates']} обновлений всех 3 022 080 параметров от прежнего рабочего родителя, Q4 на каждом проходе. Выбран шаг {selection['step']}; 0 означает возврат к прежнему рабочему профилю после непрохождения критериев сохранения.",'',
       f"Данные: {data['goals']['train']} новых задач, {data['replay_goals']} прежних условий, {data['lessons']} проверенных состояний. Непрерывные случайные числовые входы; отдельные ошибки операций, аргументов и порядка; правильный код после PUBLIC_RUNS и ошибочный код после COUNTEREXAMPLE; пересмотр неверной SPEC без показа кода. Пятьдесят процентов каждого обучающего батча заняты прежним переводом и исправлениями.",'',
       'Новый закрытый набор: 256 задач, 512 обычных эпизодов, 64 эпизода с подставленной неверной SPEC и 128 эпизодов восстановления после принудительного отклонённого DONE. Это разные диагностические режимы; их результаты не смешаны. Начальный принудительный DONE исключён из числа ложных заявлений модели.','',
       'Чекпойнт выбран до открытия закрытого теста по отдельным 96 новым задачам и 96 прежним условиям. Допустима потеря не более двух ранее верных переводов; исправления, завершение правильного кода и ложные DONE защищены относительно родителя. Дополнительно защищён прежний длинный рабочий профиль.','',
       '| Версия | Верный первый SPEC /256 | Завершено /512 | Исправлено /256 | Верный код доведён /256 | Итоговая порча | Принятые ложные DONE | Эпизоды с ложными заявлениями |',
       '|---|---:|---:|---:|---:|---:|---:|---:|']
    for role,r in reports.items():
        s=r['own']['summary'];p=r['primary']['summary'];lines.append(f"| {role} | {p['passed']} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['correct_starts_corrupted']} | {s['false_DONE']} | {s['episodes_with_false_DONE_claims']} |")
    lines+=['','| Версия | Ошибочная SPEC: завершено /64 | Ошибочная SPEC: ложные DONE | После отклонения: исправлено /64 | После отклонения: верный код доведён /64 |',
       '|---|---:|---:|---:|---:|']
    for role,r in reports.items():
        w=r['wrong']['summary'];q=r['recovery']['summary']if r['recovery']else None
        lines.append(f"| {role} | {w['passed']} | {w['false_DONE']} | {q['wrong_starts_repaired']if q else'не оценивалось'} | {q['correct_starts_completed']if q else'не оценивалось'} |")
    lines+=['','| Версия | Отказы UNSURE | Пересмотры SPEC | Отказы при изначально верном коде | Неверный кандидат при верном старте, до отката | Переполнения контекста | Ложный DONE даже относительно SPEC на аудите |',
            '|---|---:|---:|---:|---:|---:|---:|']
    policy_diagnostics={}
    for role,r in reports.items():
        records=r['own']['records'];s=r['own']['summary'];actions=collections.Counter(h['generation'].get('action')for row in records for h in row['history']if'generation'in h)
        initial_ok={p['id']for p in r['primary']['records']if p['intent']['tested_equal']}
        unnecessary_reviews=sum(x['task_id']in initial_ok and x['replans']>0 for x in records)
        good_abstain=sum(x['initially_correct']and x['abstained']for x in records)
        wrong_candidate=sum(x['initially_correct']and not x['candidate_correct_at_exit']for x in records)
        policy_diagnostics[role]={'neural_actions':dict(actions),'correct_starts_abstained':good_abstain,'wrong_candidate_on_correct_start':wrong_candidate,
                                  'review_despite_initial_SPEC_passing_goal_audit':unnecessary_reviews}
        lines.append(f"| {role} | {s['abstained']} | {s['replans']} | {good_abstain} | {wrong_candidate} | {s['context_overflows']} | {s['false_DONE_spec']} |")
    lines+=['','Пересмотры при начальной SPEC, уже прошедшей аудит цели: `'+json.dumps({k:v['review_despite_initial_SPEC_passing_goal_audit']for k,v in policy_diagnostics.items()},ensure_ascii=False)+'`.','']
    lines+=['','Режим восстановления после принудительного отказа начинает с правильной SPEC, заданной проверяющим. Он изолирует навык работы с отказом и не равен самостоятельному пониманию условия. В режиме неверной SPEC гипотеза также задаётся проверяющим. Длинный и компактный профили имеют общий предел 1024 токена; длинные входы не обрезаются, переполнение считается неудачей. Проверка DONE числовая и конечная: совпадение на её входах может не сохраниться на отдельном аудите даже относительно той же SPEC.','',
       'Выбор по development; закрытый тест в выборе не участвовал. Ниже показано, почему чекпойнт прошёл или не прошёл защитные критерии.','',
       '| Шаг | Новый перевод /96 | Завершено /96 | Исправлено /48 | Верный код доведён /48 | Ложные DONE | Неверная SPEC: ложные DONE /32 | Потеря прежних правильных переводов | Все критерии |',
       '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    rejected={}
    for step in read(ROOT/'policy.json')['checkpoints']:
        d=read(root/f'development-{step}.json');s=d['own']['summary'];w=d['wrong']['summary'];decision=read(root/f'selection-{step}.json')
        rejected[step]=[k for k,v in decision['checks'].items()if k!='lost_parent_correct_translation'and not v]
        lines.append(f"| {step} | {d['primary']['summary']['passed']} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['false_DONE']} | {w['false_DONE']} | {decision['checks']['lost_parent_correct_translation']} | {'да'if decision['key'][0]else'нет'} |")
    lines+=['','Непройденные критерии: `'+json.dumps(rejected,ensure_ascii=False)+'`.','',
       '| Сравнение | Завершения, п.п. [95% ДИ] | Исправления, п.п. [95% ДИ] | Принятые ложные DONE, п.п. [95% ДИ] |',
       '|---|---:|---:|---:|']
    for role in ['selected','final']:
        for parent_role in ['parent_compact','parent_long']:
            cells=[]
            for metric in ['completion','repairs','accepted_false_DONE']:
                q=uncertainty[role][parent_role][metric];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.1f} [{lo:+.1f}; {hi:+.1f}]")
            lines.append('| '+role+' − '+parent_role+' | '+' | '.join(cells)+' |')
    lines+=['','| Версия | Унарные /32 | Бинарные /32 | Новые композиции /160 | Константы /32 |',
       '|---|---:|---:|---:|---:|']
    for role,r in reports.items():
        p=r['primary']['by_family'];lines.append('| '+role+' | '+' | '.join(str(p[k]['passed'])for k in ['unary','binary','composition','constant'])+' |')
    lines+=['','Итоговая порча считается после механического отката неподтверждённых изменений упряжью. Дополнительно выше показаны неверные кандидаты до отката. Сопоставление SPEC и числовой проверки конечно; произвольные циклы и ветвления МК-61 этим набором не охвачены.','',
       f"Обучение использовало одну B200 рядом с пользовательским Qwen: лимит аллокатора {training['allocator_MiB_limit']} МиБ, фактический пик зарезервированной PyTorch памяти {training['peak_reserved_MiB']:.1f} МиБ. Эффективный батч 32 набран четырьмя микробатчами по 8. Между шагами и вызовами добавлены паузы; целевой duty fraction {training['GPU_duty_fraction']}. Память CUDA-контекста находится вне этого лимита. Конфигурация и контейнер Qwen из эксперимента не менялись; влияние на задержку Qwen отдельно не измерялось.",'',
       f"Q4: подтверждено {native['streams_verified']} совпадающих потоков B200/CPU/C++, повторная упаковка из сохранённых весов точна. Память и скорость физического PicoCalc не измерялись.",'',
       'Попарная неопределённость посчитана по 10 000 bootstrap-выборок из 256 задач; два начальных состояния задачи остаются вместе. Это не проверка устойчивости к seed обучения.','',
       'Артефакты: `.build/mk61-agent-20261106/spec-diverse-recovery-v1`. Рабочий профиль устройства автоматически не заменён.','']
    report.write_text('\n'.join(lines));summary={'complete':True,'selection':selection,'training':training,
       'closed':{a:{'primary':r['primary']['summary'],'own':r['own']['summary'],'wrong':r['wrong']['summary'],'recovery':r['recovery']['summary']if r['recovery']else None}for a,r in reports.items()},
       'uncertainty':uncertainty,'report':str(report),'native_streams':native['streams_verified'],'policy_diagnostics':policy_diagnostics}
    write(ROOT/'comparison.json',summary)
    path=HERE/'work-state.json';state=read(path);entry=state.get('latest_diverse_recovery_training',{})
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=1;state['total_accounted_optimizer_updates_lower_bound']+=training['optimizer_updates']
    entry.update(phase='complete',complete=True,ledger_accounted=True,optimizer_updates=training['optimizer_updates'],selection=selection,report=str(report))
    state.update(latest_diverse_recovery_training=entry,active_experiment=None,all_own_jobs_complete=True,phase='diverse_recovery_complete',
                 next_action='Keep the working parent; diagnose unnecessary SPEC reviews and test a deterministic symbolic program/SPEC view before another joint SFT course.')
    write(path,state);write(ROOT/'finish.json',{'complete':True,'ledger_accounted':True,'optimizer_updates':training['optimizer_updates'],'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print(json.dumps({'selection':selection,'closed':summary['closed'],'report':str(report)},ensure_ascii=False),flush=True)


if __name__=='__main__':main(ROOT/'server-results')
