"""Report restoration separately from fresh Q4 transfer; account actual updates."""
import time
import numpy as np
from bv_common import ROOT,HERE,read,write,rows,sha,check_frozen
from bv_eval import fit_key,protected,brief
from br_finish import paired
from be_language import paths3
from ar_spec import spec_text


def compositions(report):
    return sum(r['family']=='composition'and r['program_correct']for r in report['primary']['records'])


def fit_summary(report,parent):
    out={'nine_restored':sum(r['program_correct']for r in report['hard']['records'][:9]),
         'cosine_restored':bool(report['hard']['records'][9]['program_correct'])}
    for panel in ['retention','composition']:
        old={r['id']:r for r in parent[panel]['records']}
        out[panel]={'passed':report[panel]['summary']['passed'],'total':len(old),
            'parent_successes':sum(r['program_correct']for r in old.values()),
            'lost_ids':[r['id']for r in report[panel]['records']if old[r['id']]['program_correct']and not r['program_correct']],
            'gained_ids':[r['id']for r in report[panel]['records']if not old[r['id']]['program_correct']and r['program_correct']]}
    out['all_fit_criteria']=bool(fit_key(report,parent)[0][0])
    return out


def family_uncertainty(left,right):
    held={tuple(x)for x in read(ROOT/'ast-frozen.json')['held_triples']['closed']}
    goals={g['id']:g for g in rows(ROOT/'closed.jsonl')if g['family']=='composition'}
    families=sorted(held);idx={x:i for i,x in enumerate(families)};d=np.zeros((len(families),4))
    a={x['id']:x for x in left['own']['records']if x['family']=='composition'}
    b={x['id']:x for x in right['own']['records']if x['family']=='composition'}
    p={x['id']:x for x in left['primary']['records']};q={x['id']:x for x in right['primary']['records']}
    assert a.keys()==b.keys()
    for k,x in a.items():
        y=b[k];keys=paths3(goals[x['task_id']]['spec']['X'])&held;assert len(keys)==1
        j=idx[next(iter(keys))]
        d[j,0]+=int(y['pass'])-int(x['pass'])
        if not x['initially_correct']:d[j,1]+=int(y['pass'])-int(x['pass'])
        d[j,2]+=int(y['finished']and not y['program_correct'])-int(x['finished']and not x['program_correct'])
        if x['initially_correct']:d[j,3]+=int(q[x['task_id']]['program_correct'])-int(p[x['task_id']]['program_correct'])
    denom=np.array([len(a),len(goals),len(a),len(goals)])
    rng=np.random.default_rng(261124126);sample=rng.integers(0,len(d),size=(10000,len(d)))
    boot=d[sample].sum(1)/denom*100;point=d.sum(0)/denom*100
    return {k:{'delta_percentage_points':float(point[i]),
        'CI95_family_bootstrap':[float(v)for v in np.percentile(boot[:,i],[2.5,97.5])]}
        for i,k in enumerate(['completion','repairs','accepted_false_DONE','first_SPEC'])}


def main():
    check_frozen();root=ROOT/'server-results';policy=read(ROOT/'policy.json')
    training=read(root/'training.json');native=read(root/'native-verification.json')
    done=read(root/'controller-complete.json');post=read(root/'postflight.json')
    actual=training['optimizer_updates'];assert actual in policy['checkpoints']
    assert done['all_own_workers_joined']and native['complete']and post['Qwen_health']=='200'
    assert training['actor_parameters_unchanged']and training['teacher_parameters_unchanged']and training['frozen_translator_tensors_unchanged']
    pre=read(root/'preselected.json');choice=pre['chosen'];assert pre['closed_seen']is False
    reports={n:read(root/('closed-'+n+'.json'))for n in ['original','parent','final','selected']}
    for r in reports.values():assert len(r['primary']['records'])==256 and len(r['own']['records'])==512
    alias=read(root/'audit-roles.json')['aliases']['selected'];assert reports['selected']==reports[alias]
    parent_fit=read(ROOT/'parent-fit.json');last_fit=read(root/f'fit-{actual}.json')
    fitting={'parent':fit_summary(parent_fit,parent_fit),'final':fit_summary(last_fit,parent_fit)}
    development={};decisions={};parent_dev=read(root/'parent-development.json')
    for step in policy['checkpoints']:
        p=root/f'selection-{step}.json'
        if not p.exists():continue
        assert step<=actual
        fit=read(root/f'fit-{step}.json');score,checks=fit_key(fit,parent_fit)
        d=root/f'development-{step}.json'
        if d.exists():
            report=read(d);checks.update(protected(report,parent_dev));development[step]=brief(report)
        decision=read(p);assert score==decision['fit_key']and checks==decision['checks']
        assert decision['passed']==all(checks.values())and decision['closed_seen']is False
        decisions[step]=decision
    assert list(decisions)==[s for s in policy['checkpoints']if s<=actual]
    if choice['step']:
        assert choice['step']==actual and decisions[actual]['passed']and fitting['final']['all_fit_criteria']
    else:assert not any(x['passed']for x in decisions.values())
    parent=reports['parent'];final=reports['final'];a=parent['own']['summary'];z=final['own']['summary']
    confirmation=protected(final,parent)
    confirmation['new_compositions_retained']=compositions(final)>=compositions(parent)
    uncertainty=paired(parent['own']['records'],final['own']['records'])
    family=family_uncertainty(parent,final)
    new_selected=choice['step']>0;fit_ok=fitting['final']['all_fit_criteria']
    if fit_ok:
        conclusion='Все9 потерянных переводов и отдельный косинус восстановлены; прежние успешные переводы и композиции сохранены на контрольных примерах обучения.'
    else:
        f=fitting['final'];conclusion=(f"Восстановлено {f['nine_restored']}/9 переводов. Полный критерий восстановления и сохранения прежних успехов не пройден; цель достигнута частично.")
    selection=(f"До закрытого теста выбран новый шаг {choice['step']}."if new_selected else
        'Новый чекпойнт не прошёл весь отбор; selected оставлен исследовательским родителем BU1500. Это не замена рабочего профиля исходной модели.')
    if all(confirmation.values()):transfer='Все заданные требования к переносу сохранены на этом новом закрытом наборе.'
    else:transfer='На новом закрытом наборе есть ухудшения: '+', '.join(k for k,v in confirmation.items()if not v)+'. Это ограничивает вывод о качестве восстановления.'
    report=HERE/'SPEC_RETENTION_RECOVERY_RESULTS.md'
    lines=['# Восстановление переводов адаптера SPEC','',conclusion,'',selection+' '+transfer,'',
        f"Обучение завершено: {actual} дополнительных обновлений прежнего адаптера BU1500,317440 обучаемых коэффициентов LoRA ранга16. Q4 использован на каждом проходе и при оценке. Последний чекпойнт проверен независимо от того, прошёл ли он отбор. Рабочий профиль приложения не заменён.",'',
        '## Восстановление известных ошибок','',
        'Это учебные контрольные примеры:9 ошибок предыдущего опыта, отдельная потерянная задача с косинусом,128 старых переводов и240 старых композиций. Их использовали в replay и для отбора; они больше не являются независимым тестом. Удержание проверяется по каждому прежнему успеху, а не только по суммарному счёту.','',
        '| Контроль | BU1500 | После восстановления |',
        '|---|---:|---:|',
        f"| Потерянные переводы /9 | {fitting['parent']['nine_restored']} | {fitting['final']['nine_restored']} |",
        f"| Косинус RD → RA /1 | {int(fitting['parent']['cosine_restored'])} | {int(fitting['final']['cosine_restored'])} |"]
    for panel,label in [('retention','Старые переводы /128'),('composition','Старые композиции /240')]:
        x=fitting['parent'][panel];y=fitting['final'][panel]
        lines.append(f"| {label} | {x['passed']} | {y['passed']} |")
        lines.append(f"| Потеря прежних успехов: {panel} | 0 | {len(y['lost_ids'])} |")
    if fitting['final']['retention']['lost_ids']:
        goals={g['id']:g for g in rows(ROOT/'retention.jsonl')}
        results={r['id']:r for r in last_fit['retention']['records']}
        lines+=['','Прежние успешные переводы, потерянные этим чекпойнтом:','']
        for identifier in fitting['final']['retention']['lost_ids']:
            g=goals[identifier];r=results[identifier]
            lines.append('- '+g['task']+' Ожидалось `'+spec_text(g['spec'])+'`; получено `'+spec_text(r['declared_spec'])+'`.')
    lines+=['','| Исходная ошибка | Ожидаемая интерпретация | Восстановлена |','|---|---|---|']
    for item,r in zip(read(ROOT/'loss-analysis.json')['nine_lost'],last_fit['hard']['records'][:9]):
        lines.append('| '+item['id']+' | `'+item['expected']+'` | '+('да'if r['program_correct']else'нет')+' |')
    lines+=['','## Новый закрытый тест в Q4','',
        '256 новых условий:160 композиций из32 отложенных троек операций и по32 унарные, бинарные и числовые задачи. Два начальных состояния на условие дают512 обычных эпизодов. Отдельно64 эпизода с намеренно неверной SPEC служат стресс-проверкой. Данные и критерии были зафиксированы до обучения; выбор весов завершён до первого ответа маленькой модели на этом тесте.','',
        '| Переводчик | Первый SPEC /256 | Композиции /160 | Завершено /512 | Исправлено /256 | Верный код доведён /256 | Порча /256 | Принятые ложные DONE /512 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    labels={'original':'Исходный','parent':'BU1500','final':f'Восстановление +{actual}'}
    for n in ['original','parent','final']:
        r=reports[n];s=r['own']['summary']
        lines.append(f"| {labels[n]} | {r['primary']['summary']['passed']} | {compositions(r)} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['correct_starts_corrupted']} | {s['false_DONE']} |")
    lines+=['','| Переводчик | Все принятые DONE | Эпизоды с ложными заявлениями | Все ложные заявления | UNSURE | Переполнения | Неверная SPEC: ложные DONE /64 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    diagnostics={}
    for n in ['original','parent','final']:
        r=reports[n];s=r['own']['summary'];p={v['id']:v for v in r['primary']['records']}
        bad=[v for v in r['own']['records']if v['finished']and not v['program_correct']]
        diagnostics[n]={'accepted_false_DONE':len(bad),
            'initial_SPEC_wrong':sum(not p[v['task_id']]['intent']['tested_equal']for v in bad),
            'final_SPEC_wrong':sum(not v['final_spec_intent']['tested_equal']for v in bad),
            'own_SPEC_fails_independent_audit':sum(not v['spec_consistent']for v in bad),
            'wrong_candidate_before_rollback_on_correct_start':sum(v['initially_correct']and not v['candidate_correct_at_exit']for v in r['own']['records'])}
        lines.append(f"| {labels[n]} | {s['DONE']} | {s['episodes_with_false_DONE_claims']} | {s['false_DONE_claims']} | {s['abstained']} | {s['context_overflows']} | {r['wrong']['summary']['false_DONE']} |")
    lines+=['','Ошибки декодирования первоначальной SPEC /256: `'+str({n:reports[n]['primary']['summary']['codec_errors']for n in ['original','parent','final']})+'`. Они учитываются как неуспех, не исключаются из знаменателя.','',
        'Порча считается после предусмотренного упряжью отката незавершённых изменений. Принятые ошибочные DONE отделены от всех ложных заявлений, в том числе отклонённых проверкой. Неизменный численный gate проверяет код относительно заявленной SPEC; ошибочное понимание условия может совпадать с кодом.','',
        '## Отбор до закрытого теста','',
        'Контрольные точки200/600/1200/2400; остановка на первой, где исправлены все10 ошибок, не потерян ни один из102 успешных переводов и185 композиций BU, и не ухудшены заданные метрики нового development. Родитель заранее проверен на development. Новые чекпойнты не оценивались на нём, пока не пройден полный контроль восстановления.','',
        '| Шаг | Исправлено /9 | Косинус | Потери переводов | Потери композиций | Новый development проверен | Прошёл отбор |',
        '|---|---:|---|---:|---:|---|---|']
    for step,decision in decisions.items():
        s=fit_summary(read(root/f'fit-{step}.json'),parent_fit)
        lines.append(f"| {step} | {s['nine_restored']} | {'да'if s['cosine_restored']else'нет'} | {len(s['retention']['lost_ids'])} | {len(s['composition']['lost_ids'])} | {'да'if step in development else'нет'} | {'да'if decision['passed']else'нет'} |")
    lines+=['','Непройденные критерии по шагам: `'+str({k:[n for n,v in d['checks'].items()if not v]for k,d in decisions.items()})+'`. Selected зафиксирован как `'+alias+'` и не пересматривается по closed.','',
        '| Development | Первый SPEC /64 | Завершено /128 | Исправлено /64 | Верный код доведён /64 | Ложные DONE | Порча | Эпизоды с ложными заявлениями |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,r in [('BU1500',parent_dev),*[(str(s),read(root/f'development-{s}.json'))for s in development]]:
        s=r['own']['summary'];lines.append(f"| {name} | {r['primary']['summary']['passed']} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['false_DONE']} | {s['correct_starts_corrupted']} | {s['episodes_with_false_DONE_claims']} |")
    lines+=['','## Неопределённость','',
        'Разница восстановления с BU1500 на новом закрытом тесте.10000 попарных bootstrap-выборок по256 задачам; два начальных состояния остаются вместе. Для композиций ниже дополнительно группируются все5 условий одного семейства. Один seed обучения не измеряет разброс между повторными запусками.','',
        '| Метрика | Разница, п.п. |95% ДИ по задачам |','|---|---:|---|']
    for metric,v in uncertainty.items():
        lo,hi=v['CI95_task_bootstrap'];lines.append(f"| {metric} | {v['delta_percentage_points']:+.2f} | [{lo:+.2f}; {hi:+.2f}] |")
    lines+=['','| Только композиции | Разница, п.п. |95% ДИ по32 семействам |','|---|---:|---|']
    for metric,v in family.items():
        lo,hi=v['CI95_family_bootstrap'];lines.append(f"| {metric} | {v['delta_percentage_points']:+.2f} | [{lo:+.2f}; {hi:+.2f}] |")
    teacher=read(ROOT/'teacher-frozen.json');data=read(ROOT/'ast-frozen.json')
    lines+=['','## Обучение и проверка реализации','',
        f"Курс:10 исходных ошибок,80 новых вариантов с {teacher['counts']['train']['questions']} русскими формулировками DeepSeek,102 проверенных прежних перевода,185 проверенных композиций и3061 общий пример replay. В каждом batch32:4 точных исправления,4 варианта,8 успешных старых переводов,8 успешных композиций,8 общих примеров. После неудачной контрольной точки до4 общих мест занимают ошибки уже известных учебных контролей. Четверть примеров обучает повторному разбору условия. LR2e-5; KD0.5 только на проверенных успехах и только если argmax учителя совпадает с целевым токеном. Ошибки родителя не дистиллировались.",'',
        'Учитель DeepSeek-V4.1-Flash также выполнял слепую обратную проверку формулировок без исходного AST; для оценки использованы два запроса. Это одна большая модель, а не независимая человеческая разметка. Тройки операций и числа development/closed исключены из этого курса и проверены против известных прежних целей и наблюдавшихся гипотез. Все заранее выбранные AST сохранены после проверки формулировок. ROM проверяет вычисления и скомпилированный код, но не истинность понимания русского текста.','',
        'Входной русский словарь, embeddings, action/correctness-головы и необучаемые матрицы сохранены. Прежний actor заморожен побитно. Адаптер используется только в принудительном первоначальном WRITE и повторном разборе; обычные действия и тела WRITE по-прежнему выдаёт actor. Протокол, численная проверка, rollback,12 действий и контекст1024 FP32 KV не менялись. Точный cache повторных неизменных actor-входов экономит вычисления, не меняя ответы и лимиты.','',
        f"Нативная проверка: {native['streams_verified']} потоков токенов B200/CPU/C++ совпали. Проверена точная перепаковка Q4, исходный и родительский пакеты MKA, сохранность всех матриц кроме50 Q/V+MLP. C++ bridge переключает профили в одном буфере весов {native['one_weight_buffer_bytes']} байт. Профили хранятся отдельно; Python-оценка держала несколько моделей одновременно. Физические память и скорость PicoCalc не измерялись.",'',
        f"Одна B200, allocator≤1536МиБ, минимум8192МиБ свободно, целевая доля активного времени0.5. Пик reserved PyTorch {training['peak_reserved_MiB']:.1f}МиБ, без CUDA-контекста и внешних библиотек. Qwen не менялся, итоговый /health200. Собственный GPU-worker завершён.",'',
        'Область опыта — прямолинейные числовые выражения и запись результата в память. Вывод не распространяется на все игры, циклы и ветвления МК-61 или на доказательство корректности для всех входов.','',
        'Артефакты: `.build/mk61-agent-20261106/spec-retention-recovery-v1`; `server-results/training.json`, `preselected.json`, `fit-*.json`, `closed-*.json`, `native-verification.json`, `comparison.json`.','']
    report.write_text('\n'.join(lines))
    summary={'complete':True,'optimizer_updates':actual,'trainable_parameters':317440,'choice':choice,'selected_alias':alias,
        'fit':fitting,'all_fit_criteria':fit_ok,'closed':{n:brief(r)for n,r in reports.items()},'closed_confirmation':confirmation,
        'all_closed_protections_met':all(confirmation.values()),'development':development,'decisions':decisions,
        'uncertainty':uncertainty,'composition_family_uncertainty':family,'diagnostics':diagnostics,'actor_unchanged':True,
        'native_streams':native['streams_verified'],'Qwen_health':200,'report':str(report),'postprocessor_sha256':sha(__file__)}
    write(ROOT/'comparison.json',summary)
    state=read(HERE/'work-state.json');entry=state.get('latest_retention_spec_training',{})
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=1;state['total_accounted_optimizer_updates_lower_bound']+=actual
    entry.update(phase='complete',complete=True,optimizer_updates=actual,selected_step=choice['step'],
        ledger_accounted=True,report=str(report),all_fit_criteria=fit_ok,all_closed_protections_met=all(confirmation.values()))
    state.update(latest_retention_spec_training=entry,active_experiment=None,all_own_jobs_complete=True,
        phase='spec_retention_recovery_complete',result_report=str(report),
        next_action='Review the completed repair-versus-transfer result before another course; keep the working device profile unchanged.')
    write(HERE/'work-state.json',state)
    write(ROOT/'finish.json',{'complete':True,'optimizer_updates':actual,'ledger_accounted':True,
        'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print({'report':str(report),'optimizer_updates':actual,'fit':fitting['final'],'selected_step':choice['step'],
        'new_closed_all_protected':all(confirmation.values())},flush=True)


if __name__=='__main__':main()
