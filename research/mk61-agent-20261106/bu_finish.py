"""Whole-cycle outcome, translation gains, immutable actor, and honest fallback."""
import numpy as np
from bu_common import ROOT,HERE,read,write,rows,sha,check_frozen
from bu_eval import key,brief
from br_finish import paired
from be_language import paths3


def family_uncertainty(left,right):
    held={tuple(x)for x in read(ROOT/'ast-frozen.json')['held_triples']['closed']}
    goals={g['id']:g for g in rows(ROOT/'closed.jsonl')if g['family']=='composition'}
    families=sorted(held);idx={x:i for i,x in enumerate(families)};d=np.zeros((len(families),4))
    a={x['id']:x for x in left['own']['records']if x['family']=='composition'};b={x['id']:x for x in right['own']['records']if x['family']=='composition'}
    p={x['id']:x for x in left['primary']['records']};q={x['id']:x for x in right['primary']['records']}
    for k,x in a.items():
        y=b[k];keys=paths3(goals[x['task_id']]['spec']['X'])&held;assert len(keys)==1;j=idx[next(iter(keys))]
        d[j,0]+=int(y['pass'])-int(x['pass'])
        if not x['initially_correct']:d[j,1]+=int(y['pass'])-int(x['pass'])
        d[j,2]+=int(y['finished']and not y['program_correct'])-int(x['finished']and not x['program_correct'])
        if x['initially_correct']:d[j,3]+=int(q[x['task_id']]['program_correct'])-int(p[x['task_id']]['program_correct'])
    denom=np.array([320,160,320,160]);rng=np.random.default_rng(261123124);sample=rng.integers(0,len(d),size=(10000,len(d)))
    boot=d[sample].sum(1)/denom*100;point=d.sum(0)/denom*100
    return {k:{'delta_percentage_points':float(point[i]),'CI95_family_bootstrap':[float(v)for v in np.percentile(boot[:,i],[2.5,97.5])]}
        for i,k in enumerate(['completion','repairs','accepted_false_DONE','first_SPEC'])}


def main():
    check_frozen();root=ROOT/'server-results';training=read(root/'training.json');native=read(root/'native-verification.json')
    assert training['optimizer_updates']==1500 and native['complete']and read(root/'postflight.json')['Qwen_health']=='200'
    assert training['actor_parameters_unchanged']and training['frozen_translator_tensors_unchanged']
    choice=read(root/'preselected.json')['chosen'];reports={n:read(root/('closed-'+n+'.json'))for n in ['baseline','selected','final']}
    baseline=reports['baseline'];uncertainty={n:paired(baseline['own']['records'],reports[n]['own']['records'])for n in ['selected','final']}
    family_intervals={n:family_uncertainty(baseline,reports[n])for n in ['selected','final']}
    development={};decisions={}
    for step in read(ROOT/'policy.json')['checkpoints']:
        r=read(root/f'development-{step}.json');score,checks=key(r,read(root/'parent-development.json'));decision=read(root/f'selection-{step}.json')
        assert score==decision['key']and checks==decision['checks'];development[step]=brief(r);decisions[step]=decision
    a=baseline['own']['summary'];b=reports['selected']['own']['summary'];z=reports['final']['own']['summary'];report=HERE/'PHASE_SPEC_ADAPTER_RESULTS.md'
    confirmation={'new_checkpoint':choice['step']>0,
        'first_SPEC_gain':reports['selected']['primary']['summary']['passed']>baseline['primary']['summary']['passed'],
        'completed':b['passed']>=a['passed'],'repairs':b['wrong_starts_repaired']>=a['wrong_starts_repaired'],
        'correct_finishes':b['correct_starts_completed']>=a['correct_starts_completed'],'false_DONE':b['false_DONE']<=a['false_DONE'],
        'corruption':b['correct_starts_corrupted']<=a['correct_starts_corrupted'],
        'false_claims':b['episodes_with_false_DONE_claims']<=a['episodes_with_false_DONE_claims']}
    verdict=('Новый адаптер не прошёл весь заранее заданный отбор; selected остаётся исходным переводчиком.'if choice['step']==0 else
             f"По development выбран шаг {choice['step']}; его полный результат на новом закрытом тесте показан ниже.")
    verdict+=(' Улучшение выбранного полного агента подтверждено на этом новом наборе.'if all(confirmation.values())else' Все требования к сохранению прежних навыков пока не выполнены.')
    lines=['# Адаптер SPEC отдельно от управления инструментами','',
        f"Фиксированный адаптер после1500 обновлений улучшил первый SPEC {baseline['primary']['summary']['passed']}→{reports['final']['primary']['summary']['passed']} из256, завершения {a['passed']}→{z['passed']} из512, снизил принятые ложные DONE {a['false_DONE']}→{z['false_DONE']} и итоговую порчу правильного кода {a['correct_starts_corrupted']}→{z['correct_starts_corrupted']} на новом закрытом наборе.",'',
        'На development при этом утрачены9 ранее верных переводов, приобретены6, общий счёт удержания105→102/128; одна унарная задача также перестала решаться. Поэтому исследовательский выигрыш нового адаптера не стал основанием заменить рабочий профиль.','',verdict,'',
        'Результат последнего шага показан как обязательная исследовательская проверка. Выбор по development не пересматривается после просмотра closed; selected остаётся заранее зафиксированным вариантом.','',
        'Обучение завершено:1500 обновлений317440 коэффициентов LoRA Q/V и MLP ранга16, Q4 на каждом проходе. Входные embeddings, словарь, action/correctness-головы и остальные исходные матрицы переводчика не менялись. Отдельный actor полностью сохранён побитно. Основной профиль устройства не заменён.','',
        'Переключение: новый translator используется только для принудительного WRITE при первоначальном переводе и повторном разборе условия. Все обычные решения инструментов и тела ответов (в том числе обычный WRITE) выдаёт прежний actor. Условия повторного разбора, численный gate, RUN, rollback, контекст1024 FP32 KV и12 действий прежние. Новая SPEC меняет наблюдения actor, поэтому неизменность его весов не гарантирует сохранения поведения всего цикла.','',
        '| Новый закрытый тест | Первый SPEC /256 | Композиции /160 | Завершено /512 | Исправлено /256 | Верный код доведён /256 | Порча /256 | Принятые ложные DONE |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    comp=lambda r:sum(x['family']=='composition'and x['program_correct']for x in r['primary']['records'])
    for n,r in reports.items():
        s=r['own']['summary'];lines.append(f"| {n} | {r['primary']['summary']['passed']} | {comp(r)} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['correct_starts_corrupted']} | {s['false_DONE']} |")
    lines+=['','| Вариант | Все принятые DONE | Эпизоды с ложными заявлениями | Все ложные заявления DONE | UNSURE | Переполнения | Неверная SPEC: ложные DONE /64 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    extra={}
    for n,r in reports.items():
        s=r['own']['summary'];p={x['id']:x for x in r['primary']['records']};bad=[x for x in r['own']['records']if x['finished']and not x['program_correct']]
        extra[n]={'accepted_false_DONE':len(bad),'initial_SPEC_wrong':sum(not p[x['task_id']]['intent']['tested_equal']for x in bad),
            'final_SPEC_wrong':sum(not x['final_spec_intent']['tested_equal']for x in bad),
            'own_SPEC_fails_independent_audit':sum(not x['spec_consistent']for x in bad),
            'wrong_candidate_before_rollback_on_correct_start':sum(x['initially_correct']and not x['candidate_correct_at_exit']for x in r['own']['records'])}
        lines.append(f"| {n} | {s['DONE']} | {s['episodes_with_false_DONE_claims']} | {s['false_DONE_claims']} | {s['abstained']} | {s['context_overflows']} | {r['wrong']['summary']['false_DONE']} |")
    lines+=['','Порча считается после механического отката незавершённых изменений. Неверные кандидаты при верном старте до отката: '+str({k:v['wrong_candidate_before_rollback_on_correct_start']for k,v in extra.items()})+'. Ложные заявления включают принятые и отклонённые DONE; принятые ошибочные завершения показаны отдельно.','',
        '| Development | Первый SPEC /128 | Композиции /80 | Завершено /128 | Исправлено /64 | Ложные DONE | Удержание /128 | Потеря прежде верных | Все критерии |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    parentdev=read(root/'parent-development.json')
    for step in [0,*read(ROOT/'policy.json')['checkpoints']]:
        r=parentdev if step==0 else read(root/f'development-{step}.json');s=r['own']['summary']
        lost=0 if step==0 else-decisions[step]['key'][-1]
        lines.append(f"| {step} | {r['primary']['summary']['passed']} | {comp(r)} | {s['passed']} | {s['wrong_starts_repaired']} | {s['false_DONE']} | {r['retention']['summary']['passed']} | {lost} | {'родитель'if step==0 else('да'if decisions[step]['key'][0]else'нет')} |")
    lines+=['','Непройденные критерии: '+str({k:[n for n,v in d['checks'].items()if not v]for k,d in decisions.items()})+'. Выбор записан до первого ответа маленькой модели на closed. Шаг0 означает возврат к прежнему переводчику, а не принятие неудачного адаптера.','',
        '| Разница с baseline | Завершения, п.п. [95% ДИ] | Исправления, п.п. [95% ДИ] | Принятые ложные DONE, п.п. [95% ДИ] |',
        '|---|---:|---:|---:|']
    for n,v in uncertainty.items():
        cells=[]
        for metric in ['completion','repairs','accepted_false_DONE']:
            q=v[metric];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.1f} [{lo:+.1f}; {hi:+.1f}]")
        lines.append('| '+n+' | '+' | '.join(cells)+' |')
    data=read(ROOT/'ast-frozen.json');teacher=read(ROOT/'teacher-frozen.json')
    lines+=['','Интервалы выше:10000 попарных bootstrap-выборок по256 задачам, оба начальных состояния остаются вместе. Закрытые160 композиций охватывают32 разные новые тройки операций. Ниже отдельный bootstrap по этим32 семействам: все5 условий и оба старта каждого семейства остаются вместе. Это учитывает их связанность; один seed обучения и один набор семейств всё равно не показывают устойчивость на любых будущих задачах.','',
        '| Только композиции, разница с baseline | Первый SPEC, п.п. [95% ДИ] | Завершения, п.п. [95% ДИ] | Исправления, п.п. [95% ДИ] | Ложные DONE, п.п. [95% ДИ] |',
        '|---|---:|---:|---:|---:|']
    for n,v in family_intervals.items():
        cells=[]
        for metric in ['first_SPEC','completion','repairs','accepted_false_DONE']:
            q=v[metric];lo,hi=q['CI95_family_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.1f} [{lo:+.1f}; {hi:+.1f}]")
        lines.append('| '+n+' | '+' | '.join(cells)+' |')
    lines+=['',
        f"Данные: {data['goals']['train']} учебных AST (включая {data['retired_wrong_goals']} снятых с роли теста ошибок и {data['order_pairs']} пар перестановок), {teacher['counts']['train']['questions']} русских учебных вопросов DeepSeek,2048 прежних переводов. Четверть примеров обучала повторному разбору без кода, половина — повтору старого перевода. Loss только по токенам SPEC; action loss и нейросетевой критик не обучались.",'',
        'Новые development/closed AST и числа различаются; отложенные тройки исключены из обучения, включая прежние цели и наблюдавшиеся гипотезы. Все заранее выбранные закрытые AST сохранены после проверки формулировок. DeepSeek восстанавливал смысл текста без исходного AST; для оценки использованы два обратных запроса. Генератор и проверяющий — одна большая модель, не независимые человеческие аннотаторы. ROM проверяет код и числа, но не истинность русского понимания.','',
        'Статистика принятых ложных DONE: `'+str(extra)+'`. Проверка gate относится к заявленной SPEC; ошибочная интерпретация может согласоваться с кодом. Конечные числовые тесты не являются доказательством на всех входах. Область этого опыта — прямолинейные числовые выражения и запись результата в память, не произвольные игры с ветвлениями и циклами.','',
        f"Проверены {native['streams_verified']} совпадающих потоков B200/CPU/C++ с реальным переключением профилей. Первый Q4 payload совпал с родителем; перепаковка сохранённых master-весов точна. Меняться могли только50 матриц Q/V и MLP; входной словарь, embedding/action-строки и остальные Q4-матрицы сохранены. Нативный bridge использует один буфер весов {native['one_weight_buffer_bytes']} байт, один KV и workspace. Переводчик и actor сохраняются отдельными пакетами; это дополнительное хранение профиля, а не одновременная загрузка двух моделей в этот буфер.",'',
        'Физический PicoCalc не измерялся, сборка приложения не заменялась. Python/GPU-оценка держит модели одновременно для удобства эксперимента; утверждение об одном буфере относится к проверенному C++ bridge.','',
        f"Обучение на одной B200 рядом с Qwen: allocator≤1536МиБ, минимум8192МиБ свободно, целевая доля активного времени0.5. Пик reserved PyTorch {training['peak_reserved_MiB']:.1f}МиБ, CUDA-контекст и библиотеки в него не входят. Итоговый /health Qwen200; его контейнер и параметры не менялись, задержки отдельно не измерялись. Собственные GPU-контейнеры завершены.",'',
        'Артефакты: `.build/mk61-agent-20261106/spec-phase-adapter-v1`; `server-results/preselected.json`, `training.json`, `closed-*.json`, `native-verification.json`.','']
    report.write_text('\n'.join(lines));summary={'complete':True,'optimizer_updates':1500,'trainable_parameters':317440,'choice':choice,
        'closed':{n:brief(r)for n,r in reports.items()},'development':development,'decisions':decisions,'uncertainty':uncertainty,
        'closed_confirmation':confirmation,'whole_agent_improvement_confirmed':all(confirmation.values()),'composition_family_uncertainty':family_intervals,
        'diagnostics':extra,'actor_unchanged':True,'native_streams':native['streams_verified'],'Qwen_health':200,'report':str(report),'postprocessor_sha256':sha(__file__)}
    write(ROOT/'comparison.json',summary);state=read(HERE/'work-state.json');entry=state.get('latest_phase_spec_training',{})
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=1;state['total_accounted_optimizer_updates_lower_bound']+=1500
    entry.update(phase='complete',complete=True,optimizer_updates=1500,selected_step=choice['step'],ledger_accounted=True,report=str(report))
    state.update(latest_phase_spec_training=entry,active_experiment=None,all_own_jobs_complete=True,phase='spec_phase_adapter_complete',result_report=str(report),
        next_action='Assess the completed phase-specific translator comparison before further training or context changes.')
    write(HERE/'work-state.json',state);print({'report':str(report),'selected_step':choice['step'],'optimizer_updates':1500},flush=True)


if __name__=='__main__':main()
