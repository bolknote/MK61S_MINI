"""Publish the weight diagnosis and corrected-state overlay without doing SGD."""
import collections
import json
import time
from bn_common import ROOT,PREVIOUS,RESULTS,HERE,read,write,rows,sha,check


def main():
    check();assert read(ROOT/'postflight.json')['complete'];assert read(ROOT/'review-state-fix-checks.json')['complete']
    weight=read(ROOT/'weight-statistics.json');action=read(ROOT/'server-results/action-ablation.json');cue=read(ROOT/'server-results/prompt-cue-results.json')
    training=read(ROOT/'training-cue-audit.json');attribution=read(ROOT/'server-results/logit-attribution.json')
    cross={
        'old_long':read(RESULTS/'parent-full-development.json'),
        'old_compact':read(RESULTS/'compact-parent-full-development.json'),
        'new_compact':read(RESULTS/'full/development-3000.json'),
        'new_long':read(ROOT/'server-results/new-weights-long-development.json')}
    margins=[x for x in attribution['records']if x['source']=='new'and x['abstained']]
    mean={k:sum(x[k]for x in margins)/len(margins)for k in ['UNSURE_minus_expected_old','UNSURE_minus_expected_new','head_contribution','hidden_contribution']}
    cue_summary={}
    for name in cue['metrics']:
        transitions=cue['transitions'];cue_summary[name]={'UNSURE':sum(r['actions'][name]=='unsure'for r in transitions),
            'DONE_on_wrong_code':sum(r['actions'][name]=='done'and not r['code_correct']for r in transitions),
            'DONE_on_correct_code':sum(r['actions'][name]=='done'and r['code_correct']for r in transitions),
            'expected_actions':cue['metrics'][name]['new']['expected_action_matches']}
    mislabels=sum(training['misflagged_review_successes_actually_sampled'].values());assert mislabels==4863
    rates={k:v['unsure']/sum(v.values())for k,v in training['actions_by_review_flag'].items()}
    summary={'complete':True,'optimizer_updates':0,'models_unchanged':True,'data_bug_rows':5344,'misflagged_action_draws':mislabels,
             'UNSURE_training_rates_by_review_flag':rates,'weights':weight['summary'],'cross':{k:x['self']['summary']for k,x in cross.items()},
             'action_ablations':{k:{'avoidable_expected_action':v['new_abstentions']['avoidable_expected_action'],'avoidable_still_UNSURE':v['new_abstentions']['avoidable_still_UNSURE'],'success_controls_retained':v['new_success_controls']['retain_DONE']}for k,v in action['ablations'].items()},
             'margin_decomposition_mean':mean,'cue_interventions':cue_summary,
             'causal_limit':'Incorrect state flags and causal prompt sensitivity demonstrated; the fraction of end-to-end loss caused by the data bug still requires a corrected-training A/B.'}
    write(ROOT/'summary.json',summary)
    lines=['# Почему изменилась полная 3M после последнего обучения','',
        'Найдена конкретная ошибка подготовки данных: успешные состояния после повторного разбора SPEC импортировались с флагом «разбор ещё доступен». Это моя ошибка в генераторе учебных состояний. Она создаёт ложную связь между израсходованным разбором и отказом UNSURE. Большого общего ухудшения новых весов в прежней упряжи не обнаружено.','',
        'Это послетестовая диагностика уже открытых данных, без обучения и без нового закрытого экзамена. Исходные веса, прежние данные и результаты не изменялись.','',
        '## Контроль: веса и упряжь по отдельности','',
        'Один и тот же development: 398 условий, 192 инструментальных эпизода. Три клетки измерены до обучения/при его контрольной точке, четвёртая добавлена сейчас. Во всех случаях реальный Q4, прежний бюджет12 действий.','',
        '| Веса | Протокол | Завершения /192 | Исправления /96 | Ложные принятые DONE | Порча /96 |',
        '|---|---|---:|---:|---:|---:|']
    for k in ['old_long','new_long','old_compact','new_compact']:
        m=cross[k]['self']['summary'];lines.append('| '+k.split('_')[0]+' | '+k.split('_')[1]+' | '+' | '.join(str(m[x])for x in ['passed','wrong_starts_repaired','false_DONE','correct_starts_corrupted'])+' |')
    lines+=['','Старые и новые веса с прежней упряжью дали140 и139 завершений; ложные принятые DONE снизились10→5. В новом протоколе обучение улучшило результат89→129. Поэтому падение полного нового варианта нельзя объяснять общей порчей коэффициентов. Этот вывод ограничен данным development; новая закрытая проверка старого протокола с новыми весами не проводилась.','',
        '## Ошибка состояния инструмента','',
        '`bj_runtime.snapshot()` не сохранял `replan_attempted`; импорт старого успешного replay в `bl_lessons.py` присваивал `False`. Для5344 строк (`replay_done`:2672; `replay_repair`:2672) наблюдение явно содержало `SPEC_REVISED`, то есть разбор уже был выполнен, но новый промпт показывал «Разборов SPEC осталось:1». Правильная команда оставалась DONE или WRITE; неверным был описанный модели ресурс инструмента.','',
        'Точное повторение RNG-потока совпало по digest с обоими обучениям. Неверно размеченные состояния реально использовались4863 раза из60000 строк решений с действиями. Доля UNSURE в разметке при флаге «разбор использован» составляла36.17%, при «доступен» —3.20%. Это сильная возможность выучить побочный признак вместо проверки программы.','',
        'На512 конечных состояниях новой полной ветки187 отказов. Из них60 имели правильную гипотезу, правильную программу и выполненные RUN, то есть можно было DONE; ещё14 требовали RUN,34 — WRITE,4 — DIAG. Остальные75 соответствовали отказу при имеющейся гипотезе и бюджете. Метки взяты из уже записанных проверок настоящим ROM, а не из нового нейросетевого критика.','',
        '## Что видно в коэффициентах','',
        f"- Проверены все {weight['summary']['master']['parameters']} параметров. Относительная L2-норма изменения FP32-мастера: {100*weight['summary']['master']['relative_L2']:.3f}%; эффективных Q4-весов: {100*weight['summary']['effective_Q4']['relative_L2']:.3f}%.",
        f"- Квантованные коды изменились у {weight['summary']['Q4_codes_changed']} из {weight['summary']['Q4_codes_total']} матричных коэффициентов ({100*weight['summary']['Q4_codes_changed']/weight['summary']['Q4_codes_total']:.3f}%). Изменения масштабов групп меняют и значения коэффициентов с прежним кодом; это учтено отдельно.",
        '- Наибольший относительный Q4-дрейф среди матриц — v_proj слоя0, gate_proj слоя9, v_proj слоёв4 и5. Величина дрейфа сама по себе не показывает вред.',
        '- Возврат всех шести старых выходных строк выбора действий не устранил ни одного из112 отказов, для которых был размечен полезный следующий шаг. Число UNSURE осталось187. Возврат старых входных embeddings также не устранил эти отказы.',
        f"- Для тех112 состояний средний сдвиг логита UNSURE относительно нужного действия составил {mean['UNSURE_minus_expected_new']-mean['UNSURE_minus_expected_old']:.3f}: вклад выходных коэффициентов {mean['head_contribution']:.3f}, вклад внутренних представлений {mean['hidden_contribution']:.3f}. Симметричное билинейное разложение точно с погрешностью <1e-9; округление FP32 учтено отдельно.",
        '- Возврат старых attention/MLP либо каждого из10 слоёв по отдельности уменьшал часть отказов, но одновременно ухудшал правильные действия на контрольных состояниях. Например, возврат всех MLP снизил UNSURE187→60, но сохранённых правильных DONE стало226 вместо318. Одного безопасно заменяемого «плохого слоя» не обнаружено.',
        '- Сравнение сырого FP32-мастера с Q4 не является проверкой равнокачественных режимов: обучение использовало Q4 на каждом проходе. На этих состояниях сырой новый мастер совпал с требуемым действием165 раз, Q4 —393. Снятие квантования готовым исправлением не стало.','',
        '## Прямое вмешательство в подсказки','',
        'Одни веса и те же512 конечных состояний. Условие пользователя, код, факты RUN и гипотеза сохранялись; редактировалась только служебная проза. Это выбор следующей команды, не полный повтор инструментального цикла.','',
        '| Подсказка | UNSURE | Предложений DONE при неверном коде | Совпадение с размеченным действием |',
        '|---|---:|---:|---:|']
    for k,v in cue_summary.items():lines.append(f"| {k} | {v['UNSURE']} | {v['DONE_on_wrong_code']} | {v['expected_actions']} |")
    lines+=['','Удаление счётчика резко меняет поведение, но предложения DONE при неверном коде растут7→44. Это не измерение принятых ложных DONE: последующие проверки упряжи здесь не выполнялись. Простое удаление подсказки или случайный откат коэффициентов не считается исправлением.','',
        '## Подготовленное исправление и следующий эксперимент','',
        '- `bo_review_state_fix.snapshot()` сохраняет реальное использование разбора. Корректирующий слой для прежнего неизменяемого набора содержит5344 точечных изменения только флага; условия, программы и целевые команды сохранены.',
        '- Регрессионная проверка выполнила настоящий DIAG04→разбор SPEC и подтвердила: snapshot показывает0 оставшихся разборов, исходный код не меняется. Проверка завершена успешно.',
        '- Для проверки причинного вклада нужен повтор последнего раунда от прежнего родителя с той же выборкой, seed и параметрами, изменив только неверные флаги. Долю потери качества, вызванную именно этой ошибкой, до такого повторного обучения назвать нельзя. Для итоговой оценки нужен новый закрытый тест.',
        '- В этой диагностике optimizer updates=0. Родители и рабочий профиль сохранены.','',
        '## Артефакты','',
        f'- `{ROOT}`: заморозка, веса, matched-state logits, прямые вмешательства, точный аудит потока и коррекции.',
        '- `weight-statistics.json`: все112 тензоров, коды и масштабы Q4; `server-results/action-ablation.json`: возврат блоков.',
        '- `server-results/logit-attribution.json`: разложение каждой пары логитов; `server-results/prompt-cue-results.json`: все изменения действий от подсказок.',
        '- `review-state-corrections.jsonl`, `review-state-fix-checks.json`: подготовленное исправление и регрессионная проверка.',
        '- `postflight.json`: завершение диагностических контейнеров, проверка неизменности моделей и нулевого обучения.','']
    # Improve spacing in narrative without changing identifiers or numeric data.
    text='\n'.join(lines)
    for a,b in {'бюджет12':'бюджет 12','дали140':'дали 140','и139':'и 139','снизились10':'снизились 10','результат89':'результат 89',
                'Для5344':'Для 5344','состоялись4863':'состоялись 4863','использовались4863':'использовались 4863','из60000':'из 60000','составляла36':'составляла 36',
                '—3.20':'— 3.20','На512':'На 512','ветки187':'ветки 187','них60':'них 60','ещё14':'ещё 14',',34':', 34',',4':', 4','Остальные75':'Остальные 75',
                'слоя0':'слоя 0','слоя9':'слоя 9','слоёв4':'слоёв 4','и5':'и 5','из112':'из 112','осталось187':'осталось 187','тех112':'тех 112','из10':'из 10',
                'UNSURE187':'UNSURE 187','стало226':'стало 226','вместо318':'вместо 318','действием165':'действием 165','—393':'— 393','же512':'же 512',
                'растут7':'растут 7','содержит5344':'содержит 5344','показывает0':'показывает 0','все112':'все 112'}.items():text=text.replace(a,b)
    path=HERE/'WEIGHT_DIAGNOSIS_RESULTS.md';path.write_text(text)
    statepath=HERE/'work-state.json';state=read(statepath)
    state['latest_weight_diagnosis'].update(phase='complete',complete=True,optimizer_updates=0,report=str(path),data_bug_rows=5344,corrected_overlay=str(ROOT/'review-state-corrections.jsonl'))
    if state.get('active_experiment')=='weight-diagnosis-v1':state.update(active_experiment=None,all_own_jobs_complete=True)
    write(statepath,state)
    write(ROOT/'complete.json',{'complete':True,'optimizer_updates':0,'report':str(path),'report_sha256':sha(path),'unix':time.time(),
          'sources':{p.name:sha(p)for p in HERE.glob('bo_*.py')}})
    print(json.dumps({'complete':True,'report':str(path),'data_bug_rows':5344,'misflagged_training_draws':mislabels,'optimizer_updates':0}),flush=True)


if __name__=='__main__':main()
