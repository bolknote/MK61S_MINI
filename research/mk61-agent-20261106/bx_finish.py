"""Separate fitted repairs, phase consistency, and independent whole-agent transfer."""
import time
import numpy as np
from bx_common import ROOT,HERE,read,write,rows,sha,check_frozen
from bx_eval import selection,brief,composition_count
from bv_finish import fit_summary
from br_finish import paired
from be_language import paths3


def family_ci(left,right):
    held={tuple(x)for x in read(ROOT/'ast-frozen.json')['held_triples']['closed']};idx={v:i for i,v in enumerate(sorted(held))}
    goals={g['id']:g for g in rows(ROOT/'closed.jsonl')if g['family']=='composition'};d=np.zeros((len(idx),3))
    a={r['id']:r for r in left['own']['records']if r['family']=='composition'};b={r['id']:r for r in right['own']['records']if r['family']=='composition'}
    for k,x in a.items():
        y=b[k];keys=paths3(goals[x['task_id']]['spec']['X'])&held;assert len(keys)==1;j=idx[next(iter(keys))]
        d[j,0]+=int(y['pass'])-int(x['pass'])
        if not x['initially_correct']:d[j,1]+=int(y['pass'])-int(x['pass'])
        d[j,2]+=int(y['finished']and not y['program_correct'])-int(x['finished']and not x['program_correct'])
    den=np.array([320,160,320]);rng=np.random.default_rng(261126127);sample=rng.integers(0,len(d),(10000,len(d)))
    boot=d[sample].sum(1)/den*100;point=d.sum(0)/den*100
    return {k:{'delta_percentage_points':float(point[i]),'CI95_family_bootstrap':[float(v)for v in np.percentile(boot[:,i],[2.5,97.5])]}
        for i,k in enumerate(['completion','repairs','accepted_false_DONE'])}


def main():
    check_frozen();root=ROOT/'server-results';training=read(root/'training.json');actual=training['optimizer_updates'];policy=read(ROOT/'policy.json')
    native=read(root/'native-verification.json');assert native['complete']and read(root/'controller-complete.json')['all_own_workers_joined']
    assert read(root/'postflight.json')['Qwen_health']=='200'
    assert training['actor_parameters_unchanged']and training['teacher_parameters_unchanged']and training['frozen_translator_tensors_unchanged']and training['never_removed_regressions']
    assert training['cumulative_regressions_final']>=training['cumulative_regressions_initial']
    pre=read(root/'preselected.json');choice=pre['chosen'];assert pre['closed_seen']is False
    assert actual in policy['checkpoints']
    parent_dev=read(root/'parent-development.json');parent_fit=read(ROOT/'parent-fit.json');development={};decisions={};fits={}
    for step in policy['checkpoints']:
        if step>actual:continue
        r=read(root/f'development-{step}.json');f=read(root/f'fit-{step}.json');decision=selection(r,f,parent_dev,parent_fit)
        assert decision==read(root/f'selection-{step}.json')
        development[step]=brief(r);decisions[step]=decision;fits[step]=fit_summary(f,parent_fit)
        fits[step]['initial_fit_criteria']=fits[step].pop('all_fit_criteria')
        fits[step]['hard_replan_correct']=f['hard_replan']['summary']['passed']
    if choice['step']:assert choice['step']==actual and decisions[actual]['passed']
    reports={n:read(root/('closed-'+n+'.json'))for n in ['parent','final','selected']}
    alias=read(root/'audit-roles.json')['aliases']['selected'];assert reports['selected']==reports[alias]
    for r in reports.values():assert len(r['primary']['records'])==256 and len(r['own']['records'])==512
    baseline=reports['parent'];final=reports['final'];a=baseline['own']['summary'];b=final['own']['summary']
    p=baseline['paired']['summary'];q=final['paired']['summary']
    primary_by_id={r['id']:r for r in final['primary']['records']}
    false_done=[r for r in final['own']['records']if r['finished']and not r['program_correct']]
    diagnostics={'accepted_false_DONE':len(false_done),
        'initial_SPEC_wrong':sum(not primary_by_id[r['task_id']]['program_correct']for r in false_done),
        'final_SPEC_wrong':sum(not r['final_spec_intent']['tested_equal']for r in false_done),
        'code_matches_own_SPEC':sum(r['spec_consistent']for r in false_done)}
    confirmation={'SPEC':final['primary']['summary']['passed']>=baseline['primary']['summary']['passed'],
        'compositions':composition_count(final)>=composition_count(baseline),'completed':b['passed']>=a['passed'],
        'repairs':b['wrong_starts_repaired']>=a['wrong_starts_repaired'],'correct_finishes':b['correct_starts_completed']>=a['correct_starts_completed'],
        'false_DONE':b['false_DONE']<=a['false_DONE'],'corruption':b['correct_starts_corrupted']<=a['correct_starts_corrupted'],
        'false_claim_episodes':b['episodes_with_false_DONE_claims']<=a['episodes_with_false_DONE_claims'],
        'paired_both_correct':q['both_correct']>=p['both_correct'],'paired_spoils':q['correct_to_wrong']<=p['correct_to_wrong']}
    uncertainty=paired(baseline['own']['records'],final['own']['records']);families=family_ci(baseline,final)
    selected=reports['selected']['own']['summary'];confirmed=choice['step']>0 and all(confirmation.values())and selected['passed']>a['passed']
    report=HERE/'SPEC_PHASE_CONSISTENCY_RESULTS.md'
    verdict=(f"До закрытого теста выбран новый шаг {choice['step']}."if choice['step']else'Ни один новый чекпойнт не прошёл весь заранее заданный отбор; selected оставлен BU1500.')
    verdict+=(' Общее улучшение подтверждено на этом новом закрытом наборе.'if confirmed else' Общее улучшение полного агента на новом закрытом наборе не подтверждено.')
    lines=['# Парное обучение согласованности фаз SPEC','',verdict,'',
        f"Курс завершён: {actual} обновлений317440 коэффициентов LoRA Q/V+MLP ранга16, начиная с BU1500. Q4 на каждом проходе и при оценке. Actor, входной словарь, embeddings, action/correctness-головы и все необучаемые тензоры сохранены. Последний чекпойнт оценён даже при отказе отбора. Рабочая модель приложения не заменялась.",'',
        '## Новый закрытый тест','',
        '| Переводчик | Первый SPEC /256 | Композиции /160 | Завершено /512 | Исправлено /256 | Верный код доведён /256 | Порча | Принятые ложные DONE |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in ['parent','final']:
        r=reports[name];s=r['own']['summary'];label='BU1500'if name=='parent'else f'Парный курс +{actual}'
        lines.append(f"| {label} | {r['primary']['summary']['passed']} | {composition_count(r)} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['correct_starts_corrupted']} | {s['false_DONE']} |")
    lines+=['','256 новых условий:160 композиций из32 новых троек операций и по32 унарные, бинарные и числовые задачи. Два старта на условие дают512 обычных эпизодов. Дополнительно64 стресс-эпизода с неверной SPEC. AST, числа, формулировки и критерии выбора зафиксированы до обучения; выбор весов завершён до первого ответа модели на closed.','',
        '| Переводчик | Эпизоды с ложными заявлениями | Все ложные заявления DONE | UNSURE | Переполнения | Стресс: ложные DONE /64 | Ошибки формата SPEC /256 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name in ['parent','final']:
        r=reports[name];s=r['own']['summary'];lines.append(f"| {name} | {s['episodes_with_false_DONE_claims']} | {s['false_DONE_claims']} | {s['abstained']} | {s['context_overflows']} | {r['wrong']['summary']['false_DONE']} | {r['primary']['summary']['codec_errors']} |")
    lines+=['','Порча считается после предусмотренного rollback. Принятые ложные DONE отделены от всех ошибочных заявлений, включая отклонённые проверкой. Численный gate проверяет код относительно заявленной SPEC, поэтому неправильное понимание условия всё ещё может пройти проверку.','',
        'Диагностика принятых ложных DONE финальной ветки: `'+str(diagnostics)+'`. Неверный первоначальный перевод и неверная конечная гипотеза посчитаны отдельно; программа может согласоваться со своей SPEC и не решать исходное условие.','',
        '## Согласованность независимо от решения actor','',
        'Для каждого условия отдельно запрошены первый перевод и повторный разбор без кода, с тем же набором констант и remaining6. Пробы выполняются для всех256 условий, поэтому не зависят от того, решил ли actor повторить разбор. Согласованность сама по себе не означает верность: отдельно посчитаны правильные ответы обеих фаз. Равенство — по числовым аудитам, не буквальное совпадение AST.','',
        '| Переводчик | Первый верен | Повторный верен | Оба верны | Верный → неверный | Неверный → верный | Смысл совпал |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name in ['parent','final']:
        s=reports[name]['paired']['summary'];lines.append(f"| {name} | {s['initial_correct']} | {s['replan_correct']} | {s['both_correct']} | {s['correct_to_wrong']} | {s['wrong_to_correct']} | {s['semantic_agreement']} |")
    lines+=['','Условная статистика реально выполненных повторных разборов в циклах: `'+str({name:reports[name]['own']['replan']for name in ['parent','final']})+'`. Эти популяции могут различаться между моделями; сырые доли нельзя считать сравнением одной и той же случайной выборки.','',
        '## Контрольные точки и известные ошибки','',
        '| Шаг | Восстановлено /9 | Косинус | Те же10 задач: повторный разбор | Потери старых переводов | Потери старых композиций |',
        '|---|---:|---|---:|---:|---:|']
    for step,f in fits.items():lines.append(f"| {step} | {f['nine_restored']} | {'да'if f['cosine_restored']else'нет'} | {f['hard_replan_correct']} | {len(f['retention']['lost_ids'])} | {len(f['composition']['lost_ids'])} |")
    lines+=['','Это учебные контроли, снятые с роли независимого теста. Их восстановление не является оценкой переноса на новые задачи.','',
        '| Development | Первый SPEC /128 | Оба разбора верны /128 | Верный → неверный /128 | Завершено /256 | Исправлено /128 | Ложные DONE | Порча |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,r in [('BU1500',parent_dev),*[(str(step),read(root/f'development-{step}.json'))for step in development]]:
        s=r['own']['summary'];v=r['paired']['summary'];lines.append(f"| {name} | {r['primary']['summary']['passed']} | {v['both_correct']} | {v['correct_to_wrong']} | {s['passed']} | {s['wrong_starts_repaired']} | {s['false_DONE']} | {s['correct_starts_corrupted']} |")
    lines+=['','Каждый чекпойнт оценивался по полным циклам, даже если контроль восстановления не пройден. Принималась первая точка с восстановлением10 известных задач в обеих фазах, сохранением всех102 прежних переводов и185 композиций, неухудшением заданных метрик и минимум2 дополнительными завершениями development. Остановка на первой такой точке.','',
        'Непройденные критерии: `'+str({step:[k for k,v in d['checks'].items()if not v]for step,d in decisions.items()})+'`. Selected зафиксирован как `'+alias+'` до closed и не пересматривается по его результатам.','',
        '## Неопределённость','',
        'Разница финального курса с BU1500.10000 попарных bootstrap-выборок по256 условиям; оба начальных состояния остаются вместе. Один seed обучения не измеряет разброс повторных обучений.','',
        '| Метрика | Разница, п.п. |95% ДИ по задачам |','|---|---:|---|']
    for metric,v in uncertainty.items():
        lo,hi=v['CI95_task_bootstrap'];lines.append(f"| {metric} | {v['delta_percentage_points']:+.2f} | [{lo:+.2f}; {hi:+.2f}] |")
    lines+=['','| Только композиции | Разница, п.п. |95% ДИ по32 семействам |','|---|---:|---|']
    for metric,v in families.items():
        lo,hi=v['CI95_family_bootstrap'];lines.append(f"| {metric} | {v['delta_percentage_points']:+.2f} | [{lo:+.2f}; {hi:+.2f}] |")
    data=read(ROOT/'ast-frozen.json');teacher=read(ROOT/'teacher-frozen.json')
    lines+=['','## Что изменилось в обучении','',
        f"Данные: {data['regression_goals']} ранее наблюдавшихся ошибок,487 успешных примеров для удержания,96 пар контрпримеров,64 дополнительных выражения и3061 пример общего replay. Подготовлены {teacher['counts']['train']['questions']} новых русских учебных формулировок с обратной проверкой DeepSeek; новые development128 и closed256. Все прежние оценочные панели, использованные для ошибок и replay, сняты с роли независимого теста.",'',
        'Batch32 состоит из16 пар. Каждая пара содержит первоначальный и повторный перевод одной формулировки с одинаковым расположением констант и одинаковым целевым телом SPEC. Повторный разбор получает remaining3..11, первоначальный12. Семантические контрпримеры используют общую таблицу констант, чтобы порядок и лишние операции нельзя было угадывать по её составу. Пары включают повтор/лишнюю операцию, порядок функций, перестановку аргументов и знак. Различимость целей подтверждена числовым контрпримером; сами программы проверены ROM.','',
        'Loss: gold CE для обеих фаз,0.1 JS между распределениями на совпадающих целевых позициях,0.25 KD от замороженного BU1500 только на проверенных успехах и только на токенах, где argmax учителя совпал с правильной меткой. JS не подменяет правильные метки. Action loss и нейросетевой критик не обучались.','',
        f"Список усиленного повтора — объединение всех ранее найденных регрессий; исправившиеся примеры не удаляются. В начале {training['cumulative_regressions_initial']}, в конце {training['cumulative_regressions_final']} целей. Один слот берётся из текущих ошибок учебного контроля, второй — из всей истории. Ошибки нового development не добавлялись в обучение.",'',
        'В каждом batch:2 пары точных известных ошибок,2 пары накопленных регрессий,4 цели из2 семантических контрастов,3 успешных старых перевода,3 успешные композиции,1 общий replay и1 новое выражение. LR1e-5, AdamW, clipping1, microbatch4, accumulation8. Родитель — BU1500, не адаптер после неудачного курса восстановления.','',
        'Генератор и два обратных проверяющих запроса DeepSeek-V4.1-Flash — одна большая модель, не независимая человеческая разметка. Отложенные AST не отбрасывались после ответов маленькой модели. Тройки операций и числа development/closed проверены против известных прежних целей и наблюдавшихся гипотез и исключены из курса.','',
        'Один учебный текст с двойным минусом потребовал явно заданной пошаговой формулировки: первоначальный учитель многократно терял neg(-0.4375). Все ошибочные варианты отклонены, AST сохранён. Уточнённый текст дважды разобран DeepSeek без исходного AST; обе проверки восстановили нужный знак и порядок. Источник отмечен в данных, аудит сохранён.','',
        '## Исполнение','',
        'Переводчик используется только для принудительного первого WRITE и повторного разбора. Все обычные действия и тела WRITE выдаёт прежний actor. Gate, RUN, rollback, контекст1024 FP32 KV и лимит12 действий не менялись. Точный cache повторных запросов используется только для неизменного actor; ответы обучаемого переводчика не переиспользуются между чекпойнтами.','',
        f"Проверены {native['streams_verified']} совпадающих потоков B200/CPU/C++, включая обе фазы. Q4 точно пересобран из сохранённого master; первый Q4 payload совпал с BU1500. Нативный bridge использует один буфер весов {native['one_weight_buffer_bytes']} байт, KV {native['KV_bytes']} байт и workspace {native['workspace_bytes']} байт. Физические память и скорость PicoCalc не измерялись.",'',
        f"На одной B200 рядом с Qwen: allocator≤1536МиБ, минимум8192МиБ свободно, целевая доля активного времени0.5. Пик reserved PyTorch {training['peak_reserved_MiB']:.1f}МиБ без CUDA-контекста и внешних библиотек. До SGD проведён backward на парном batch4 длиной1000 без optimizer updates. После работы /health Qwen200; собственный worker завершён.",'',
        'Область опыта — прямолинейные числовые выражения с записью результата в память, не произвольные игры, циклы и ветвления. Конечные числовые проверки не доказывают корректность для всех входов.','',
        'Артефакты: `.build/mk61-agent-20261106/spec-phase-consistency-v1`; `server-results/training.json`, `priority-updates.json`, `preselected.json`, `development-*.json`, `closed-*.json`, `native-verification.json`, `comparison.json`.','']
    report.write_text('\n'.join(lines))
    result={'complete':True,'optimizer_updates':actual,'trainable_parameters':317440,'choice':choice,'selected_alias':alias,
        'fit':fits,'development':development,'decisions':decisions,'closed':{name:brief(r)for name,r in reports.items()},
        'closed_confirmation':confirmation,'whole_agent_improvement_confirmed':confirmed,'uncertainty':uncertainty,'composition_family_uncertainty':families,'false_DONE_diagnostics':diagnostics,
        'native_streams':native['streams_verified'],'actor_unchanged':True,'regressions_never_removed':True,'report':str(report),'postprocessor_sha256':sha(__file__)}
    write(ROOT/'comparison.json',result)
    s=read(HERE/'work-state.json');entry=s.get('latest_phase_consistency_training',{})
    if not entry.get('ledger_accounted'):
        s['completed_training_runs']+=1;s['total_accounted_optimizer_updates_lower_bound']+=actual
    entry.update(phase='complete',complete=True,optimizer_updates=actual,selected_step=choice['step'],ledger_accounted=True,report=str(report),whole_agent_improvement_confirmed=confirmed)
    s.update(latest_phase_consistency_training=entry,phase='spec_phase_consistency_complete',active_experiment=None,all_own_jobs_complete=True,result_report=str(report),
        next_action='Review paired phase correctness versus full-cycle transfer before another training course.')
    write(HERE/'work-state.json',s);write(ROOT/'finish.json',{'complete':True,'optimizer_updates':actual,'ledger_accounted':True,'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print({'complete':True,'optimizer_updates':actual,'selected_step':choice['step'],'whole_agent_improvement_confirmed':confirmed,'report':str(report)},flush=True)


if __name__=='__main__':main()
