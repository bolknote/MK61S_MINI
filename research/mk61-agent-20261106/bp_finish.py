"""Report both matched causal endpoints and the fresh, preselected Q4 exam."""
import json
import time
from bp_common import ROOT,PREVIOUS,PRIOR_RESULTS,HERE,read,write,sha,check_frozen


def main():
    check_frozen();r=ROOT/'server-results'
    for n in ['complete.json','native-verification.json','postflight.json']:assert read(r/n)['complete']
    training={a:read(r/a/'training.json')for a in ['lora','full']};assert all(x['optimizer_updates']==3000 for x in training.values())
    expected=read(ROOT/'repeat-plan.json')['original_draw_digest'];assert all(x['draw_digest']==expected for x in training.values())
    selection=read(r/'preselected.json');reports={a:read(r/a/'closed.json')for a in ['parent_lora','parent_full','bad_lora','bad_full','fixed3000_lora','fixed3000_full','lora','full']}
    keys=['wrong_starts_repaired','correct_starts_corrupted','false_DONE','passed','episodes_with_false_DONE_claims','abstained']
    summary={'complete':True,'optimizer_updates':6000,'corrected_rows':5344,'same_original_draws':True,'selection':selection,'causal':{},'product':{}}
    lines=['# Повтор обучения с исправленным состоянием разбора SPEC','',
           'Обе ветки завершили по 3000 шагов от тех же BJ fixed6000 родителей. Единственное изменение учебного набора — 5344 флага replan_attempted=False→True. Остальные поля, целевые команды, valid IDs, policy, seed и фактический порядок выборки сохранены. Совпадение digest с прежними обоими обучениями проверено.','',
           'Проверка Q4, контекст1024, резерв160, вычисления и KV FP32. Упряжь прежняя компактная: её подсказки не удалялись. Основной профиль и физический PicoCalc не изменялись.','',
           '## Прямое сравнение на прежнем development','',
           'Это уже открытые данные, не новый закрытый экзамен. Сравниваются финальные веса3000 с неверными и исправленными флагами.','',
           '| Ветка | Исправления /96 | Порча /96 | Ложные принятые DONE /192 | Завершения /192 | Отказы |',
           '|---|---:|---:|---:|---:|---:|']
    for a in ['lora','full']:
        before=read(PRIOR_RESULTS/a/'development-3000.json')['self']['summary'];after=read(r/a/'development-3000.json')['self']['summary']
        lines.append('| '+a+' | '+' | '.join(f'{before[k]} → {after[k]}'for k in ['wrong_starts_repaired','correct_starts_corrupted','false_DONE','passed','abstained'])+' |')
    count=read(ROOT/'teacher-frozen.json')['counts']
    lines+=['','## Новый закрытый тест: эффект исправления данных','',
            f"Новых условий: {count['questions']}; панели: {json.dumps(count['panels'],ensure_ascii=False)}. В инструментальной части512 эпизодов, поровну с правильными и ошибочными исходными программами. Новые числа и формулы отделены до SGD. Формулировки проверял DeepSeek-V4.1-Flash в двух слепых подачах без исходного AST; это один учитель, не человеческая независимая проверка.",'',
            'Одинаковый компактный runtime. Старые ошибочно обученные веса3000 и исправленный повтор3000 оценены на одном новом тесте. Здесь нет смешения эффекта нового промпта и весов.','',
            '| Ветка | Исправления /256 | Порча /256 | Ложные принятые DONE /512 | Завершения /512 | Эпизоды с ложными заявлениями DONE | Отказы |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    for a in ['lora','full']:
        old=reports['bad_'+a];new=reports['fixed3000_'+a];b=old['self']['summary'];c=new['self']['summary']
        summary['causal'][a]={'bad_flags':b,'fixed_flags':c,'bad_NLU':old['primary']['natural'],'fixed_NLU':new['primary']['natural']}
        lines.append('| '+a+' | '+' | '.join(f'{b[k]} → {c[k]}'for k in keys)+' |')
    lines+=['','Перевод естественных условий без инструментального цикла:','','| Ветка | Неверные флаги | Исправленные флаги |','|---|---:|---:|']
    for a in ['lora','full']:
        b=summary['causal'][a]['bad_NLU'];c=summary['causal'][a]['fixed_NLU'];lines.append(f"| {a} | {b['passed']}/{b['total']} | {c['passed']}/{c['total']} |")
    lines+=['','## Версии, выбранные до открытия теста','',
            'Выбор сделан по прежнему development с прежним критерием: не ухудшать исправления, завершения, порчу, принятые ложные DONE, эпизоды с ложными заявлениями, язык и формальные задачи относительно рабочего родителя. Финальный шаг3000 выше проверен независимо от выбора. Шаг0 — настоящий возврат к прежним весам и длинной упряжи.','',
            '| Ветка | Шаг | Исправления /256 | Порча /256 | Ложные принятые DONE /512 | Завершения /512 |',
            '|---|---:|---:|---:|---:|---:|']
    for a in ['lora','full']:
        b=reports['parent_'+a]['self']['summary'];c=reports[a]['self']['summary'];summary['product'][a]={'parent':b,'selected':c,'step':selection['branches'][a]['step']}
        lines.append('| '+a+' | '+str(selection['branches'][a]['step'])+' | '+' | '.join(f'{b[k]} → {c[k]}'for k in ['wrong_starts_repaired','correct_starts_corrupted','false_DONE','passed'])+' |')
    lines+=['','## Проверки и границы вывода','',
            '- B200 проверяет до первого SGD побитовое равенство исходного Q4 и FP32-мастера собственному родителю. Все3000 обновлений используют Q4 на каждом проходе.',
            '- Снимок настоящего цикла DIAG→разбор сохраняет replan_attempted=True и исходную программу. Все5344 исправленные строки проверены в трёх вариантах таблицы констант на допустимую длину.',
            '- Число отложенных проверок или отсутствие ложных DONE не доказывает произвольную корректность. Самопроверка зависит от гипотезы, которую сеть получила из условия; семантика оценивается отдельным скрытым эталоном.',
            '- Распределение теста сохранено: прямолинейные выражения, регистры и запись результата. Циклы и ветвления не проверены.',
            '- `server-results/native-verification.json` содержит загрузку реального Q4 и сравнения потоков токенов B200/CPU/C++. Физические скорость и RAM PicoCalc не измерялись.',
            '- `server-results/postflight.json` подтверждает завершение своих контейнеров, неизменность замороженных входов и сохранение основного профиля.','',
            '## Артефакты','',
            '- `.build/mk61-agent-20261106/spec-review-flag-fix-v1/frozen.json`: родители, контрольные ошибочно обученные модели, данные, код и тест до SGD.',
            '- `repeat-plan.json`, `training-inputs.json`: точное описание единственного исправления и сохранённых настроек.',
            '- `server-results/{bad_lora,bad_full,fixed3000_lora,fixed3000_full}/closed.json`: прямое сравнение на новом тесте.',
            '- `server-results/{parent_lora,parent_full,lora,full}/closed.json`: рабочие родители и выбранные версии.',
            '- `server-results/export/`: HF, MKQB, MKA и точный профиль runtime каждой роли.','']
    text='\n'.join(lines)
    for x,y in {'контекст1024':'контекст 1024','резерв160':'резерв 160','веса3000':'веса 3000','повтор3000':'повтор 3000','части512':'части 512',
                'Шаг0':'Шаг 0','шаг3000':'шаг 3000','Все3000':'Все 3000','Все5344':'Все 5344'}.items():text=text.replace(x,y)
    report=HERE/'SPEC_REVIEW_FLAG_FIX_RESULTS.md';report.write_text(text)
    write(ROOT/'summary.json',summary)
    p=HERE/'work-state.json';state=read(p);entry=state['latest_review_flag_repeat']
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=6000
    entry.update(phase='complete',complete=True,optimizer_updates=6000,ledger_accounted=True,report=str(report),selection=selection,causal=summary['causal'])
    if state.get('active_experiment')=='spec-review-flag-fix-v1':state.update(active_experiment=None,all_own_jobs_complete=True)
    write(p,state);write(ROOT/'finish.json',{'complete':True,'optimizer_updates':6000,'ledger_accounted':True,'report_sha256':sha(report),'unix':time.time()})
    print(json.dumps({'complete':True,'report':str(report),'causal':summary['causal'],'selection':selection},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
