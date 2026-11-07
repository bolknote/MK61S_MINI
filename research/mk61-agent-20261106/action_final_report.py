"""Russian, cross-checked conclusion after both bounded rounds and native probes."""
import json
import re
from pathlib import Path
from aa_common import HERE,read,write,sha
from tasks import BUILD


def compact(tool):return {k:v for k,v in tool.items()if k!='details'}


def status(row):
    if row['pass']:return 'верно, DONE'
    if row.get('model_declared_done')and row.get('program_correct'):return 'ранний DONE'
    if row.get('model_declared_done'):return 'неверный DONE'
    if row.get('model_abstained'):return 'UNSURE'
    return 'не завершено'


def main():
    first=BUILD/'action-alignment-v1/server-results';root=BUILD/'action-alignment-v2/server-results'
    assert json.loads((root/'native-verification.json').read_text())['complete']
    pre=json.loads((root/'preselected.json').read_text());native=json.loads((root/'native-verification.json').read_text())
    baseline=json.loads((root/'old-v3-final.json').read_text());demos=json.loads((root/'user-reproductions.json').read_text())
    results={a:json.loads((root/(a+'-audit.json')).read_text())for a in ['sft','preference']}
    selected_result=results[pre['selected_arm']];selected_tools=selected_result['tools']
    final_ready=bool(pre['release_eligible']and selected_tools['false_DONE']==0 and selected_tools['passed']>=400
                     and selected_result['isa']['passed']==648 and selected_result['legacy']['passed']>=66)
    lines=['# 3M Q4: обучение действий и отладки','',
           'Выполнены два отдельных опыта на двух B200: всего6600 обновлений оптимизатора, два общих этапа подготовки и четыре обученные ветки. Исходный снимок harness-debug-v3 сохранён. Все новые модели обучались с Q4 с первого обновления.','',
           'Проверяли отдельный loss выбора действия, короткую диагностическую гипотезу DIAG, исправления PATCH, запуск1–4 открытых случаев и UNSURE. После коротких этапов добавляли состояния текущих учеников; обе сравниваемые ветки получали один и тот же корпус и одинаковые SFT-выборки. Дополнительная DPO-цель обучала только предпочтения действий.','',
           'В первом опыте смена формата и дообучение сопровождались снижением прежних навыков. Во втором компактное действие используется как выходной сигнал, а перед HEX детерминированно подставляется знакомый нейросети префикс. Он не выбирает инструкции и не вычисляет ответ. Отдельное кодирование синтетического < устраняет слияние BPE. Пилот без SGD воспроизвёл131/131 прежних программ. После дальнейшего обучения старые навыки снова просели.','',
           'Во втором опыте:400 обновлений только7 выходных векторов, затем по1200 обновлений двух полных моделей. Основные веса обновлялись с LR2e-6, векторы действий —2e-5. Исходные строки русских и HEX-эмбеддингов остаются побитно одинаковыми.','',
           'Новый итоговый экзамен второго опыта:250 русских задач,500 эпизодов — ошибочная и правильная стартовая программа на каждую задачу. Включены эквивалентные варианты с NOP. Правильное завершение требует прохождения всех шести проверочных состояний, явного DONE и остановленных запусков всех открытых случаев на текущей версии кода. Отказ и тайм-аут не считаются решением. Выбор снимков выполнен по validation до итогового экзамена.','',
           '| Система | Код с первой попытки | Верное исправление + DONE | Верный код + DONE | Подтверждены все открытые случаи | Ложный DONE |',
           '|---|---:|---:|---:|---:|---:|']
    old=baseline['strict_tools']
    lines.append(f'| Исходная v3 и прежний harness | {baseline["language"]["passed"]}/250 | {baseline["tools"]["repaired"]}/250 | {baseline["tools"]["passed"]}/500 | {old["passed"]}/500 | {old["false_DONE"]} |')
    for arm,label in [('sft','SFT'),('preference','SFT + предпочтения')]:
        r=results[arm];t=r['tools']
        semantic_repaired=sum(row['finished']and row['program_correct']and not row['initially_correct']for row in t['details'])
        semantic_done=sum(row['finished']and row['program_correct']for row in t['details'])
        lines.append(f'| {label} | {r["language"]["passed"]}/250 | {semantic_repaired}/250 | {semantic_done}/500 | {t["passed"]}/500 | {t["false_DONE"]} |')
    lines+=['','Подтверждение всех открытых случаев улучшилось. Способность исправлять программу по смыслу и точность исходного кодера ухудшились. У старой системы98 случаев с верным кодом и DONE не покрыли все открытые входы; этот процедурный недостаток учитывается отдельно от семантической ошибки. Цель надёжной отладки не достигнута.']
    lines+=['','Сравнение с исходной системой включает и обучение, и изменения harness. Внутри второго опыта между SFT и DPO общие данные, формат, начальные веса и SFT-выборки совпадают.','',
            '| Ветка | Этап выбранного снимка | Сохранение команд | Старые формулы | UNSURE | Правильный код без DONE |',
            '|---|---:|---:|---:|---:|---:|']
    for arm,r in results.items():
        t=r['tools'];lines.append(f'| {arm} | {pre["choices"][arm]["stage"]} | {r["isa"]["passed"]}/648 | {r["legacy"]["passed"]}/98 | {t["abstained"]} | {t["unfinished_correct"]} |')
    readiness='выполнен'if final_ready else'не выполнен'
    lines+=['',f'По validation выбран **{pre["selected_arm"]}**. Критерий готовности на независимом экзамене: **{readiness}**. Требовались ноль ложных DONE, не менее80% правильных завершений,648/648 команд и минимум66/98 прежних формул. Критерий не ослаблялся после получения результатов.','',
            'Нулевое число ошибок на конечном наборе само по себе не доказывает правильность для произвольных задач. Свободный русский запрос не задаёт независимый исполнимый критерий приёмки. Интерактивный runner возвращает `model_declared_done` отдельно от `verified_task_success:null`.','',
            '## Воспроизведения пользовательских ошибок','',
            '| Запрос / старт | Исходная v3 | SFT | DPO | Нативный выбранный пакет |',
            '|---|---|---|---|---|']
    labels=['Синус22°, старт с косинусом','Число0, старт с1','Квадрат X, старт с двойным квадратом','(X+1)*(X+1), пустая программа']
    for i,label in enumerate(labels):
        values=[status(demos[a]['reproductions'][i])for a in ['old-v3','sft','preference','native-selected']]
        lines.append('| '+label+' | '+' | '.join(values)+' |')
    lines+=['','## Проверки исполнения','']
    for arm,r in native['models'].items():
        lines.append(f'- {arm}: точная повторная упаковка и загрузка Q4; CPU/B200 {r["cpu_matches"]}/{r["probes"]}, C++/B200 {r["native_matches"]}/{r["probes"]}; MKA {r["package_bytes"]:,} байт; FP32 KV для1024 токенов {r["cache_bytes"]:,} байт; workspace {r["workspace_bytes"]:,} байт.')
    lines+=[f'- C++-разборщик действий: {native["parser"]["state_bytes"]} байт,1027 сверок аргументов и допустимых токенов. Вычислительные веса и память KV имеют прежние размеры.',
            '- Скорость и пиковая память на физическом PicoCalc в этом опыте не измерялись.','',
            '## Что именно выучено и что осталось','',
            'DIAG — обученная гипотеза о байте и позиции, не доказательство рассуждения. Runtime возвращает фактический байт по указанному адресу и позволяет продолжить правку даже после ошибочной гипотезы. Эталоны и скрытые случаи не участвуют в ответах инструментов; их читают отдельные offline-учитель и оценщик.','']
    for arm,r in results.items():
        citations=[h.get('citation_matches_actual')for row in r['tools']['details']for h in row['history']if h['kind']=='diag']
        unknown=demos[arm]['unknown_passed']
        lines.append(f'- {arm}: фактическая ссылка DIAG совпала с кодом {sum(x is True for x in citations)}/{len(citations)} раз; явную нехватку условия распознал в {unknown}/8 дополнительных запросах после отбора.')
    tasks={t['id']:t for t in read(root/'fresh.jsonl')}
    bad=next((row for row in results[pre['selected_arm']]['tools']['details']if row['finished']and not row['program_correct']),None)
    if bad:
        task=tasks[bad['id']]
        lines+=['','Пример оставшейся ошибки выбранной ветки:',f'> {task["task"]}',
                '',f'Сеть объявила DONE с HEX-телом `'+ ' '.join(f'{b:02X}'for b in(bad['body']or[]))+'`; независимая проверка задачи не пройдена.']
    lines+=['','Первый опыт сохранён в [ACTION_ALIGNMENT_RESULTS.md](ACTION_ALIGNMENT_RESULTS.md), подробный второй — в [ACTION_ALIGNMENT_V2_RESULTS.md](ACTION_ALIGNMENT_V2_RESULTS.md). У этих опытов разные итоговые наборы, поэтому их числа не являются прямым сравнением на одних задачах.','',
            f'Исследовательский пакет: `{root/"export/selected-research"}`. Запуск: `ab_chat.py --model PATH --angle DEG --inputs JSON [--native] QUESTION`. Новый пакет требует этого протокола действий. Автоматического обновления устройства не выполнялось.']
    report=HERE/'ACTION_TRAINING_RESULTS.md'
    prose=re.sub(r'(?<=[А-Яа-яЁё])(?=\d)|(?<=\d)(?=[А-Яа-яЁё])',' ','\n'.join(lines))
    prose=prose.replace('LR2e-6','LR 2e-6')
    report.write_text(prose+'\n')
    summary={'report':str(report),'source_on_same_final':{'language':[baseline['language']['passed'],250],'tools':compact(old)},
             'selected':pre['selected_arm'],'validation_release_eligible':pre['release_eligible'],'final_release_eligible':final_ready,
             'new':{a:{'language':[r['language']['passed'],250],'tools':compact(r['tools']),
                       'isa':[r['isa']['passed'],648],'legacy':[r['legacy']['passed'],98]}for a,r in results.items()},
             'new_updates_total':6600,'native_verified':True,'source_unchanged':True}
    write(root/'final-comparison.json',summary)
    path=HERE/'work-state.json';state=json.loads(path.read_text())
    state.update(phase='action_training_comparison_complete',active_experiment=None,all_own_jobs_complete=True,
                 next_action='Review measured limits; no automatic device deployment.',result_report=str(report))
    state['latest_training_outcome']={'report':str(report),'selected_research_artifact':str(root/'export/selected-research/model.mka'),
                                     'automatic_DONE_goal_met':final_ready,'all_own_jobs_complete':True,
                                     'new_optimizer_updates':6600,'source_checkpoint_preserved':True}
    state['limitations']=['Finite regression tests do not prove arbitrary MK-61 program correctness.',
                          'Compact DIAG/action outputs do not demonstrate general natural-language reasoning.',
                          'No independent semantic success checker is available for unrestricted user questions.',
                          'Physical PicoCalc peak RAM and speed were not measured.',
                          'Historical corpus contains462 normalized listings and selected prose from9 books.']
    write(path,state);print(json.dumps({'report':str(report),'selected':pre['selected_arm'],'ready':final_ready}),flush=True)


if __name__=='__main__':main()
