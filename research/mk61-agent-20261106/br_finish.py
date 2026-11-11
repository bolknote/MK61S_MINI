"""Summarize the completed finite test; account only actual finished SGD updates."""
import json
import time
import numpy as np
from br_common import ROOT,HERE,read,write,sha,check_frozen


def paired(a,b):
    left={r['id']:r for r in a};right={r['id']:r for r in b};assert left.keys()==right.keys()
    tasks=sorted({r['task_id']for r in a});d=np.zeros((len(tasks),4));idx={k:i for i,k in enumerate(tasks)}
    for k,x in left.items():
        y=right[k];j=idx[x['task_id']]
        d[j,0]+=int(y['pass'])-int(x['pass'])
        if not x['initially_correct']:d[j,1]+=int(y['pass'])-int(x['pass'])
        d[j,2]+=int(y['finished']and not y['program_correct'])-int(x['finished']and not x['program_correct'])
        if x['initially_correct']:d[j,3]+=int(not y['program_correct'])-int(not x['program_correct'])
    denom=np.array([len(a),len(tasks),len(a),len(tasks)]);rng=np.random.default_rng(261120119)
    sample=rng.integers(0,len(tasks),size=(10000,len(tasks)));boot=d[sample].sum(1)/denom*100;point=d.sum(0)/denom*100
    return {k:{'delta_percentage_points':float(point[i]),'CI95_task_bootstrap':[float(v)for v in np.percentile(boot[:,i],[2.5,97.5])]}for i,k in enumerate(['completion','repairs','accepted_false_DONE','corruption'])}


def main():
    check_frozen();root=ROOT/'server-results';assert read(root/'complete.json')['complete']
    assert read(root/'baseline-complete.json')['complete'];assert read(root/'native-verification.json')['complete']
    policy=read(ROOT/'policy.json');choices=read(root/'preselected.json')['branches'];roles={'baseline':{}}
    for panel in policy['held_out']:roles['baseline'][panel]=read(root/('baseline-'+panel+'.json'))
    for arm in ['small','large']:
        for label in read(root/arm/'held-out-summary.json'):
            roles[arm+'_'+label]={panel:read(root/arm/(label+'-'+panel+'.json'))for panel in policy['held_out']}
    uncertainty={panel:{mode:paired(roles['small_selected'][panel]['modes'][mode]['records'],roles['large_selected'][panel]['modes'][mode]['records'])
                 for mode in ['own','gold','wrong']}for panel in policy['held_out']}
    write(ROOT/'paired-uncertainty.json',{'larger_minus_small':uncertainty,'method':'10000 paired task-cluster bootstrap draws; both starts stay together',
          'task_clusters_per_panel':32,'training_seed_uncertainty_measured':False})
    fit={arm:read(root/arm/f"selection-{choices[arm]['step']}.json")['checks']for arm in ['small','large']}
    smallfits=fit['small']['training_states_and_cycles_fit'];largefits=fit['large']['training_states_and_cycles_fit']
    verdict=('3M прошла заранее заданный порог освоения учебных состояний и циклов. Предел ёмкости на этой конечной задаче не обнаружен.'if smallfits else
             '3M не прошла весь заранее заданный порог. Это результат конечного бюджета обучения, а не доказательство предела ёмкости.')
    report=HERE/'CAPACITY_CLEAN_CYCLES_RESULTS.md'
    lines=['# Проверка освоения циклов: 3M и 5M в Q4','',verdict,'',
      'Сравнение завершено: две B200, по 3000 полных обновлений, одинаковые данные и порядок примеров, Q4 на каждом обучающем проходе. Рабочий профиль устройства не заменён.','',
      'Узкий курс улучшил у 3M завершение циклов на новых формулировках: 40→58 из 64, и новых входных числах: 41→57. На новых композициях завершения упали 33→27, а первоначальный разбор условия — 32→25 из 32. У 5M на композициях 29/64 завершений: общего преимущества увеличения модели этот опыт не установил. Различия размеров малы относительно неопределённости по 32 задачам.','',
      'Следующий контролируемый шаг — обучать прежнего рабочего родителя 3M на разнообразных числовых состояниях и композициях, сохраняя в смеси прежний перевод условий в SPEC. Полные циклы должны включать восстановление после отклонённого DONE и пересмотр неверной SPEC. Эти 32 учебные задачи полезны как регрессия освоенных действий; одним их повтором обобщение не обеспечено. Это рекомендация для следующего опыта, эффективность такой смеси здесь не измерялась.','',
      '## Устройство опыта','',
      'Взята прежняя рабочая полная 3M: 3 022 080 параметров, 10 слоёв. Версия 5M: 4 991 360 параметров, 20 слоёв. Между прежними блоками вставлены копии с нулевыми выходными проекциями attention и MLP; все параметры затем обучались. Исходная функция совпадает: 16 CPU-проверок скрытых состояний в FP32 и Q4 дали разницу 0; шесть Q4-потоков совпали на CPU, исходные B200-метрики обеих веток также совпали.','',
      'Учебный набор: 32 формулы, все 18 унарных и пять бинарных операций, девять композиций, 864 различных состояния. Правильный и ошибочный код, правильная и ошибочная SPEC, DIAG 04, пересмотр SPEC без показа кода, WRITE, RUN 00/01, DONE и UNSURE. Разметка построена из реальных переходов эмулятора; противоречий для одинаковых промптов нет. Ошибка прежних флагов пересмотра исправлена.','',
      'Контекст 1024, запас ответа 160, максимум 12 действий. Выбор чекпойнта сделан только по учебным состояниям и циклам, до генераций на контрольных панелях. На контрольных панелях затем проверены выбранный и последний чекпойнты, если они различаются; исходный общий родитель проверен отдельно после выбора.','',
      'Порог: ≥99% действий, ≥98% точных последовательностей SPEC/тел ответов при teacher forcing, ≥98% полных циклов с правильной и специально ошибочной начальной SPEC; ноль принятых ложных DONE и порчи кода во всех трёх режимах. Teacher forcing сам по себе не засчитывается как успешная отладка.','',
      '## Освоение учебного набора','',
      '| Ветка | Шаг | Действия | Точные тела при teacher forcing | Циклы со своей SPEC | Циклы gold+wrong | Ложные DONE, все режимы | Порча, все режимы | Порог |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for arm in ['small','large']:
        for step in [0,*policy['checkpoints']]:
            st=read(root/arm/f'states-{step}.json')['summary'];ev=read(root/arm/f'train-{step}.json');ch=read(root/arm/f'selection-{step}.json')['checks']
            lines.append(f"| {arm} | {step} | {st['action_correct']}/{st['action_total']} | {st['body_exact']}/{st['body_total']} | {ev['modes']['own']['summary']['passed']}/64 | {ch['diagnostic_gold_wrong_cycles']}/128 | {ch['false_DONE']} | {ch['corruption']} | {'да'if ch['training_states_and_cycles_fit']else'нет'} |")
    lines+=['',f"Выбраны: 3M — шаг {choices['small']['step']}; 5M — шаг {choices['large']['step']}. На каждый шаг обе ветки получили те же 32 примера; digest всей последовательности: `{read(root/'small/training.json')['draw_digest']}`.",'',
       '## Контрольные панели: свой разбор условия','',
       'В каждой панели 32 задачи и 64 эпизода: половина начинается с правильного кода, половина с одной заранее проверенной ошибочной программы. «Числа» — новые входные числовые значения при прежней формуле и формулировке; это не проверка новых констант в тексте. Новые AST содержат тройки унарных операций, отложенные ещё от обучения родителя.','',
       '| Панель | Версия | SPEC/программа с первого раза | Завершено | Верный код доведён из 32 | Исправлено из 32 | Порча из 32 | Принятые ложные DONE | Эпизоды с ложными заявлениями DONE |',
       '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    names={'wording':'Формулировки','inputs':'Числа','new_ast':'Новые AST'}
    for panel in policy['held_out']:
        for role,panels in roles.items():
            e=panels[panel];p=e['primary']['summary'];s=e['modes']['own']['summary']
            lines.append(f"| {names[panel]} | {role} | {p['passed']}/32 | {s['passed']}/64 | {s['correct_starts_completed']} | {s['wrong_starts_repaired']} | {s['correct_starts_corrupted']} | {s['false_DONE']} | {s['episodes_with_false_DONE_claims']} |")
    lines+=['','Порча в таблице относится к итоговому коду после механического отката неподтверждённых кандидатов. Ноль в этой колонке не доказывает, что модель никогда не предлагала ошибочных изменений. Ниже отдельно показаны неверные кандидаты в конце эпизода с изначально правильным кодом.','',
       '| Панель | Версия | Неверный кандидат при верном старте | Из них откат упряжью |',
       '|---|---|---:|---:|']
    candidate_checks={}
    for panel in policy['held_out']:
        candidate_checks[panel]={}
        for role,panels in roles.items():
            rr=panels[panel]['modes']['own']['records'];bad=[r for r in rr if r['initially_correct']and not r['candidate_correct_at_exit']]
            candidate_checks[panel][role]={'wrong_candidate_at_exit_on_correct_start':len(bad),'rolled_back':sum(r['rollback']for r in bad)}
            lines.append(f"| {names[panel]} | {role} | {len(bad)}/32 | {sum(r['rollback']for r in bad)} |")
    lines+=['','## Диагностика политики отдельно от перевода условия','',
       'Gold подставляет правильную начальную SPEC, wrong — заранее проверенную ошибочную. Это диагностические режимы с известным эталоном; они не являются оценкой самостоятельного агента. Во всех режимах решения о следующих действиях остаются за сетью.','',
       '| Панель | Версия | Gold: завершено | Wrong: завершено | Wrong: принятые ложные DONE |',
       '|---|---|---:|---:|---:|']
    for panel in policy['held_out']:
        for role,panels in roles.items():
            m=panels[panel]['modes'];g=m['gold']['summary'];w=m['wrong']['summary']
            lines.append(f"| {names[panel]} | {role} | {g['passed']}/64 | {w['passed']}/64 | {w['false_DONE']} |")
    lines+=['','## Неопределённость сравнения размеров','',
       'Разница 5M минус 3M для выбранных чекпойнтов, режим своей SPEC. Интервал 95% по 10 000 попарных bootstrap-выборок из 32 задач; оба начальных состояния задачи остаются вместе. Разброс от seed обучения этим не измерен.','',
       '| Панель | Завершения, п.п. | Исправления, п.п. | Ложные принятые DONE, п.п. |',
       '|---|---:|---:|---:|']
    for panel in policy['held_out']:
        cells=[]
        for k in ['completion','repairs','accepted_false_DONE']:
            q=uncertainty[panel]['own'][k];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.1f} [{lo:+.1f}; {hi:+.1f}]")
        lines.append('| '+names[panel]+' | '+' | '.join(cells)+' |')
    native=read(root/'native-verification.json')
    lines+=['','## Экспорт и пределы вывода','',
       f"Пересборка Q4 из сохранённых весов дала точное совпадение payload; проверено {native['streams_verified']} совпадающих потоков токенов B200/CPU/C++. Словарь и идентификаторы входных токенов одинаковы. Нативная проверка использует FP32 KV на компьютере; физическая скорость и RAM PicoCalc здесь не измерялись.",'',
       '| Версия | MKA, байт | KV при 1024 на host, байт | Workspace, байт |',
       '|---|---:|---:|---:|']
    for role,x in native['models'].items():lines.append(f"| {role} | {x['mka_bytes']} | {x['cache_bytes']} | {x['workspace_bytes']} |")
    lines+=['','Опыт проверяет конечный набор числовых формул и одну ошибочную программу на задачу. Простые учебные формулы могли встречаться родителю; это намеренная проверка освоения состояний, не новый экзамен по всему МК-61. Здесь нет произвольных ветвлений, циклов и доказательства корректности на всех числах. Приём DONE проверяет программу относительно заявленной SPEC, поэтому неверное понимание условия всё ещё может пройти проверку.','',
       'Результат одного бюджета и одного seed не доказывает ни абсолютный потолок 3M, ни отсутствие пользы от большей модели. Увеличена глубина, изменена динамика оптимизации; к ёмкости это сравнение не сводится. Контрольных задач мало для выводов по разнице в один-два эпизода.','',
       'Артефакты: `.build/mk61-agent-20261106/capacity-clean-cycles-v1`; основные результаты — `server-results`, `paired-uncertainty.json`, `server-results/native-verification.json`.','']
    report.write_text('\n'.join(lines))
    summary={'complete':True,'optimizer_updates':6000,'fit':fit,'choices':choices,'capacity_limit_proven':False,'verdict':verdict,
             'held_out':{role:{panel:{'primary':ev['primary']['summary'],'modes':{k:v['summary']for k,v in ev['modes'].items()}}for panel,ev in panels.items()}for role,panels in roles.items()},
             'native_streams':native['streams_verified'],'report':str(report),'uncertainty':uncertainty,'wrong_candidates':candidate_checks}
    write(ROOT/'comparison.json',summary)
    p=HERE/'work-state.json';state=read(p);entry=state.get('latest_capacity_diagnostic',{})
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=6000
    entry.update(phase='complete',complete=True,optimizer_updates=6000,ledger_accounted=True,report=str(report),fit=fit,choices=choices)
    state.update(latest_capacity_diagnostic=entry,active_experiment=None,all_own_jobs_complete=True,phase='clean_capacity_comparison_complete',
        next_action='Interpret clean fitting versus AST transfer; keep the existing working product profile until broader retention is measured.')
    write(p,state);write(ROOT/'finish.json',{'complete':True,'optimizer_updates':6000,'ledger_accounted':True,'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print(json.dumps({'fit':fit,'choices':choices,'report':str(report),'native_streams':native['streams_verified']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
