"""Report the completed harness ablation without counting any new training."""
import collections
import time
from pathlib import Path
from bt_common import ROOT,HERE,SOURCE,CONFIGS,read,write,sha,check_frozen
from bt_eval import key,brief
from br_finish import paired


def diagnostics(report):
    rows=report['own']['records'];good={r['id']for r in report['primary']['records']if r['intent']['tested_equal']}
    actions=collections.Counter(h['generation'].get('action')for r in rows for h in r['history']if'generation'in h)
    visible=collections.Counter()
    for r in rows:
        for h in r['history']:
            c=h.get('visible_program_check')
            if c:
                visible[c['label']]+=1
                if h['kind']in ['done','done_rejected']:visible['DONE_after_'+c['label']]+=1
    bad=[r for r in rows if r['finished']and not r['program_correct']]
    errors=collections.Counter(h['generation']['codec_error']for r in rows for h in r['history']if h.get('generation',{}).get('codec_error'))
    return {'actions':dict(actions),'visible_checks':dict(visible),'generation_error_kinds':dict(errors),
       'accepted_false_DONE':{'count':len(bad),'initial_SPEC_wrong':sum(r['task_id']not in good for r in bad),
           'final_SPEC_wrong':sum(not r['final_spec_intent']['tested_equal']for r in bad),
           'own_SPEC_also_fails_independent_audit':sum(not r['spec_consistent']for r in bad)},
       'review_despite_initial_SPEC_passing_goal_audit':sum(r['task_id']in good and r['replans']>0 for r in rows),
       'wrong_candidate_before_rollback_on_correct_start':sum(r['initially_correct']and not r['candidate_correct_at_exit']for r in rows),
       'correct_starts_abstained':sum(r['initially_correct']and r['abstained']for r in rows),
       'by_family':{f:{'total':len(v),'completed':sum(r['pass']for r in v),
             'repairs':sum(r['pass']and not r['initially_correct']for r in v),
             'false_DONE':sum(r['finished']and not r['program_correct']for r in v)}
             for f in sorted({r['family']for r in rows})for v in [[r for r in rows if r['family']==f]]}}


def main():
    check_frozen();root=ROOT/'server-results';complete=read(root/'complete.json');assert complete['complete']and complete['optimizer_updates']==0
    assert read(root/'controller-complete.json')['all_own_workers_joined'];assert read(root/'postflight.json')['Qwen_health']=='200'
    native=read(root/'native-verification.json');assert native['complete'];timing=read(root/'native-timing.json');prepared=read(root/'native-prepared.json')
    selection=read(root/'preselected.json');roles=complete['closed_evaluated'];reports={n:read(root/('closed-'+n+'.json'))for n in roles}
    development={n:read(root/('diagnostic-'+n+'.json'))for n in CONFIGS}
    assert selection['closed_seen']is False
    for n,r in development.items():score,checks=key(r,development['baseline']);assert score==selection['scores'][n]and checks==selection['checks'][n]
    uncertainty={n:paired(reports['baseline']['own']['records'],r['own']['records'])for n,r in reports.items()if n!='baseline'}
    extras={n:diagnostics(r)for n,r in reports.items()};report=HERE/'HARNESS_SYMBOLIC_CONTEXT_RESULTS.md'
    selected=selection['selected'];challenger=selection['challenger']
    base=reports['baseline']['own']['summary'];candidate=reports[challenger]['own']['summary']
    verdict=('По заранее заданным защитным условиям выбран '+selected+'.'if selected!='baseline'else
             'Ни один изменённый протокол не прошёл все защитные условия. Выбранным остаётся baseline; '+challenger+' проверен как исследовательский кандидат.')
    lines=['# Контекст и символьное наблюдение без обучения','',
       f"Контекст 1536 с FP16 KV поднял завершения {base['passed']}→{candidate['passed']} из 512 и исправления {base['wrong_starts_repaired']}→{candidate['wrong_starts_repaired']} из 256. Но принятые ложные DONE выросли {base['false_DONE']}→{candidate['false_DONE']}, итоговая порча правильного кода — {base['correct_starts_corrupted']}→{candidate['correct_starts_corrupted']}. Увеличение окна без изменения политики не принято как улучшение рабочего агента.",'',
       'Формула программы и MATCH/MISMATCH в испытанном текстовом формате также не дали улучшения без обучения: при окне 1536 на открытой диагностике завершения снизились 75→62 из 128 относительно HEX с тем же окном. Эта ветка не прошла в новый закрытый тест.','',verdict,'',
       'Опыт завершён. Веса прежнего рабочего родителя 3M неизменны, Q4 во всех режимах, обновлений оптимизатора — ноль. Рабочий профиль устройства автоматически не заменён.','',
       'Сначала пять вариантов проверены на 64 уже открытых задачах прежнего опыта. Выбор записан до генераций на новом закрытом наборе: 256 задач, 512 обычных эпизодов, отдельно по 64 с внедрённой неверной и верной SPEC. Эти диагностические режимы не смешиваются с автономным результатом.','',
       '| Вариант | Контекст | Хранение KV | Наблюдение кода |', '|---|---:|---|---|']
    for n,c in CONFIGS.items():lines.append(f"| {n} | {c['context']} | {c['KV']} | {'формула + численная проверка по SPEC'if c['symbolic']else'прежний HEX'} |")
    lines+=['','| Диагностика | Первый SPEC /64 | Завершено /128 | Исправлено /64 | Верный код доведён /64 | Порча /64 | Ложные DONE | Все критерии |',
       '|---|---:|---:|---:|---:|---:|---:|---|']
    for n,r in development.items():
        s=r['own']['summary'];lines.append(f"| {n} | {r['primary']['summary']['passed']} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['correct_starts_corrupted']} | {s['false_DONE']} | {'да'if selection['scores'][n][0]else'нет'} |")
    failures={n:[k for k,v in d.items()if not v]for n,d in selection['checks'].items()}
    lines+=['','Непройденные критерии: `'+str(failures)+'`. При равенстве сохраняется более простой исходный вариант. Сравнение завершения, исправлений, сохранения кода и ложных DONE проводится совместно; уменьшение ошибок за счёт массового отказа само по себе улучшением не считается.','',
       'FP16/FP32 при контексте 1024 дали одинаковые основные семантические метрики на 64 диагностических задачах. Это не тождество всех ответов: целые потоки токенов совпали для 63/64 первых SPEC и 126/128 обычных эпизодов; в двух внедрённых режимах — 32/32 каждый. На других запросах округление может изменить ответ.','',
       '| Новый закрытый тест | Первый SPEC /256 | Завершено /512 | Исправлено /256 | Верный код доведён /256 | Порча /256 | Принятые ложные DONE | Эпизоды с ложными заявлениями |',
       '|---|---:|---:|---:|---:|---:|---:|---:|']
    for n,r in reports.items():
        s=r['own']['summary'];lines.append(f"| {n} | {r['primary']['summary']['passed']} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['correct_starts_corrupted']} | {s['false_DONE']} | {s['episodes_with_false_DONE_claims']} |")
    lines+=['','Доля ошибок среди принятых DONE: '+', '.join(f"{n}: {r['own']['summary']['false_DONE']}/{r['own']['summary']['DONE']}"for n,r in reports.items())+'. Счётчик ложных заявлений ниже включает и принятые, и отклонённые попытки; число отклонённых ложных попыток равно этому счётчику минус принятые ложные DONE.']
    lines+=['','| Вариант | Переполнения контекста | UNSURE | Все попытки DONE | Ложные заявления DONE | Пересмотры SPEC | Пересмотры при исходно верной SPEC | Неверный кандидат при верном старте, до отката |',
       '|---|---:|---:|---:|---:|---:|---:|---:|']
    for n,r in reports.items():
        s=r['own']['summary'];d=extras[n];lines.append(f"| {n} | {s['context_overflows']} | {s['abstained']} | {s['all_DONE_claims']} | {s['false_DONE_claims']} | {s['replans']} | {d['review_despite_initial_SPEC_passing_goal_audit']} | {d['wrong_candidate_before_rollback_on_correct_start']} |")
    lines+=['','| Вариант | Неверная SPEC: завершено /64 | Неверная SPEC: ложные DONE | Верная SPEC: завершено /64 | Верная SPEC: исправлено /32 |',
       '|---|---:|---:|---:|---:|']
    for n,r in reports.items():
        w=r['wrong']['summary'];g=r['gold']['summary'];lines.append(f"| {n} | {w['passed']} | {w['false_DONE']} | {g['passed']} | {g['wrong_starts_repaired']} |")
    lines+=['','| Разница с baseline | Завершения, п.п. [95% ДИ] | Исправления, п.п. [95% ДИ] | Принятые ложные DONE, п.п. [95% ДИ] |',
       '|---|---:|---:|---:|']
    for n,u in uncertainty.items():
        cells=[]
        for k in ['completion','repairs','accepted_false_DONE']:
            q=u[k];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.1f} [{lo:+.1f}; {hi:+.1f}]")
        lines.append('| '+n+' | '+' | '.join(cells)+' |')
    lines+=['','Диагностика принятых ложных DONE:','']
    for n,d in extras.items():
        b=d['accepted_false_DONE'];lines.append(f"- {n}: всего {b['count']}; начальная SPEC неверна у {b['initial_SPEC_wrong']}, конечная — у {b['final_SPEC_wrong']}; несоответствие даже своей SPEC на отдельном аудите — {b['own_SPEC_also_fails_independent_audit']}. Ошибки генерации: `{d['generation_error_kinds']}`.")
    lines+=['','Интервалы: 10 000 попарных bootstrap-выборок по задачам, оба начальных состояния остаются вместе. Это один замороженный набор; 160 составных задач используют шесть новых троек операций. Интервал по задачам не описывает полностью разброс между новыми семействами формул; повторяемость на других распределениях не установлена.','',
       '| Вариант | Семейство | Первый SPEC | Завершено | Исправлено | Принятые ложные DONE |',
       '|---|---|---:|---:|---:|---:|']
    for n,r in reports.items():
        for f,d in extras[n]['by_family'].items():
            pp=[x for x in r['primary']['records']if x['family']==f]
            lines.append(f"| {n} | {f} | {sum(x['program_correct']for x in pp)}/{len(pp)} | {d['completed']}/{d['total']} | {d['repairs']}/{d['total']//2} | {d['false_DONE']} |")
    lines+=['',
       'Формула выводится из текущего кода, а MATCH/MISMATCH/UNKNOWN — из проверки по текущей заявленной SPEC. Проверяющий не видит эталонную русскую интерпретацию. MATCH означает только совпадение на 16 проверочных входах. Отдельный аудит использует 32 других входа и эталон цели. Ошибочная SPEC может согласоваться с ошибочным кодом. Поэтому принятие ложного DONE относительно условия остаётся возможным. Символьный декодер дополнительно проверен на всех 640 начальных программах обоих наборов: 48 числовых входов на программу, расхождений с ROM нет. Это проверка наблюдения, не результат решения задач моделью.','',
       'Не изменялись численный шлюз DONE, автозапуск недостающих RUN, бюджет 12 действий и откат незавершённых правок. Итоговая порча считается после этого отката; неверные кандидаты показаны отдельно. Символьная ветка заменяет HEX только для поддержанного прямолинейного кода. Произвольные циклы и ветвления этим тестом не охвачены.','',
       'Новая текстовая запись не оказалась короче: в 128 сопоставленных начальных состояниях открытого набора (при одной и той же верной SPEC, без генераций) формула, статус и пояснение добавляют в среднем 62 токена, диапазон +34…+94. Поэтому symbolic1024 измеряет эффект конкретной новой записи вместе с её расходом контекста; сравнение combined1536 с context1536 помогает оценить её отдельно при большем окне. Этот опыт без обучения не доказывает, что сеть не сможет освоить более компактное символьное наблюдение после адаптации.','',
       '| Вариант | MKA, байт | Реальный KV, байт | Workspace частного прототипа, байт | Сумма этих трёх, МиБ |',
       '|---|---:|---:|---:|---:|']
    for n in ['baseline','half1024','context1536']:
        t=timing['results'][n+':512'];m=prepared['packages'][n]['mka_bytes'];kv=t['KV_bytes'];w=t['workspace_bytes']
        lines.append(f'| {n} | {m} | {kv} | {w} | {(m+kv+w)/2**20:.3f} |')
    lines+=['','Объём KV подтверждён фактической ёмкостью C++-буфера, а не только теоретической формулой. Размер MKA — размер пакета для одного профиля. В частном прототипе входной текстовый буфер увеличен до 16 КиБ, поэтому workspace больше прежней сборки. Сумма не является измерением пиковой RAM процесса: она не включает эмулятор, harness, стек, аллокатор, UI, запас общего буфера для переключения профилей и другие расходы устройства; полного размещения на PicoCalc она не доказывает.','',
       '| Хост, фиксированный поток | Prefill, токенов | Prefill, секунд (медиана) | Decode, токенов/с (медиана) |',
       '|---|---:|---:|---:|']
    for name,t in timing['results'].items():lines.append(f"| {name.split(':')[0]} | {t['prefill_tokens']} | {t['prefill_seconds_median']:.4f} | {t['decode_tokens_per_second_median']:.1f} |")
    lines+=['','Один прогрев и три измерения, одинаковые входные токены и 32 фиксированных токена продолжения. Это скорость компьютера; скорость PicoCalc не измерялась. Конверсия FP32↔FP16 в этом простом прототипе добавляет работу. Уменьшение памяти не означает ускорения.','',
       f"Проверено {prepared['half_rounding_checks']} преобразований в IEEE FP16, 22 предварительных потока CPU/C++ (включая вход 1447 токенов) и {native['streams_verified']} потоков закрытого опыта B200/CPU/C++. Повторная упаковка Q4 из сохранённых весов точна; входной словарь, веса и исходный родитель сохранены. Код продукта не изменён.",'',
       f"На B200 использовался один процесс с лимитом allocator 1536 МиБ и целевой долей активного времени 0,5. Пик reserved PyTorch: {complete['peak_reserved_MiB']:.1f} МиБ; CUDA-контекст и библиотеки в этот показатель не входят. При свободной памяти менее 8192 МиБ процесс ждёт. Контейнер и настройки Qwen не менялись; итоговая проверка /health вернула 200. Влияние на задержки Qwen отдельно не измерялось.",'',
       'Артефакты: `.build/mk61-agent-20261106/harness-symbolic-context-v1`; выбор — `server-results/preselected.json`, результаты — `closed-*.json`, технические проверки — `native-*.json`. Закрытый тест после просмотра не используется для перенастройки этих вариантов.','']
    report.write_text('\n'.join(lines))
    summary={'complete':True,'optimizer_updates':0,'selected':selected,'challenger':challenger,'closed_evaluated':roles,
       'diagnostic':{n:brief(r)for n,r in development.items()},'closed':{n:brief(r)for n,r in reports.items()},
       'uncertainty':uncertainty,'diagnostics':extras,'native_streams':native['streams_verified'],'report':str(report),
       'parent_mka_sha256':sha(SOURCE/'model.mka'),'selection_used_closed':False,'Qwen_health':200,'main_profile_changed':False}
    write(ROOT/'comparison.json',summary);state=read(HERE/'work-state.json')
    state.update(active_experiment=None,all_own_jobs_complete=True,phase='harness_symbolic_context_complete',
        next_action='Assess the frozen harness comparison before choosing a targeted training course.',
        result_report=str(report),latest_harness_context_experiment={**state.get('latest_harness_context_experiment',{}),
            'phase':'complete','complete':True,'optimizer_updates':0,'selected':selected,'challenger':challenger,'report':str(report),'Qwen_health':200})
    write(HERE/'work-state.json',state);print({'report':str(report),'selected':selected,'optimizer_updates':0})


if __name__=='__main__':main()
