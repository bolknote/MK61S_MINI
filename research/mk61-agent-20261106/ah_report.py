"""Report retention, new-instance performance, and actual Q4/native checks."""
import argparse
import json
from pathlib import Path
from ah_common import HERE,ARMS,read,write
from ae_report import auc,brief


def load(root,name):return json.loads((root/name).read_text())


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    pre=load(root,'preselected.json');data=load(root,'data-frozen.json');policy=load(root,'policy.json')
    native=load(root,'native-verification.json');demos=load(root,'user-reproductions.json');prepared=load(root,'prepared.json')
    initial=load(root,'initial-fresh-audit.json');results={arm:load(root,arm+'-fresh-audit.json')for arm in ARMS}
    terminal={arm:load(root,arm+'/terminal-fresh-audit.json')for arm in ARMS}
    all_results=[('Исходный balanced',initial),*results.items()];selected=pre['selected_arm'];choice=pre['choices'][selected]
    updates=len(ARMS)*policy['blocks']*policy['steps_per_block'];summary={}
    b=initial['main']['raw'];d=terminal['distill']['main']['raw']
    lines=['# 3M Q4: сохранение навыков при обучении отладке','',
      f'Итоговые веса distill на новом основном экзамене: {b["passed"]} → {d["passed"]} из {b["total"]}, ложные DONE {b["false_DONE"]} → {d["false_DONE"]}. Они сохранены отдельным исследовательским профилем. Выбранный профиль остаётся блоком {choice["block"]}: новый чекпойнт не прошёл все условия сохранения контрольных показателей.','',
      'Продолжен balanced из false-done-v1, блок 2. Обе ветки используют прежние LoRA rank16 и после слияния содержат 3 022 080 параметров. Входной русский словарь, 1024 токена контекста, HEX/FF-кодирование и пять команд инструмента сохранены. Компилятор остаётся отдельным неизменяемым профилем.','',
      f'Добавлено {data["lessons"]:,} размеченных шагов, {data["completion_lessons"]:,} шагов проверки/завершения, сохранено {data["retention_lessons"]:,} прежних шагов. Для удержания поведения выбраны {data["anchors"]} уникальных решений balanced из строго успешных эпизодов прежнего экзамена. WRITE дополнительно проверен ROM-эмулятором, RUN/DONE/TRACE согласованы с учителем. Неверные ответы прежней модели не копируются. Прежний экзамен теперь часть обучения.','',
      'Новые пары требуют различать операцию, регистр, константу, X²/X⁴ и бинарные действия при одинаковых исходных программах, таблицах констант и тестовых входах. Половина учебных таблиц констант согласованно переставляется. Практика завершения включает следующий непроверенный RUN 01/02/03 и DONE без переписывания уже правильной программы. В парах на регистр интерфейс показывает входы регистров, названных в условии: реальное исполнение и результаты совпадают, но отображённые входы этих пар также различаются вместе с текстом цели.','',
      'Replay и distill получают одинаковые SFT-выборки по 64 строки, включая старые навыки, новые составные задачи, контрастные пары и текущие ошибки учеников. Индексы RUN выбираются равномерно среди доступных 01/02/03. Только distill дополнительно сохраняет распределения замороженной старой Q4-модели: KL для пяти действий и 23 токенов HEX-тела, температура 2, вес 2, 16 подтверждённых старых решений на обновление. Новый большой LLM-учитель не вызывался. Замороженный учитель не добавляет параметров на устройстве.','',
      f'Выполнено **{updates} обновлений**: {policy["blocks"]} × {policy["steps_per_block"]} на каждую ветку. LR LoRA и служебных голов 5e−5. Q4 присутствует в каждом прямом проходе. Перед SGD совпали исходный пакет и все 50 адаптируемых матриц; потери имеют конечные градиенты, учитель не изменяется. Проверка не выполняла обновлений оптимизатора.','',
      'Контроль и экзамен зафиксированы до SGD; точные тексты задач не пересекаются с обучением и прежними наборами. Это новые экземпляры и формулировки знакомых семейств. Основной экзамен: 240 задач, 480 верных/ошибочных стартов. Отдельно 72 контрастные задачи (288 эпизодов), 48 X²/X⁴ (192 эпизода), 64 запуска с исходным компилятором. Прежние 33 ошибки focused — учебное воспроизведение, в выборе весов не участвуют.','',
      '| Вариант | Решено /480 | Исправлено /240 | Завершено верных /240 | Ложных DONE | UNSURE |','|---|---:|---:|---:|---:|---:|']
    for name,r in all_results:
        t=r['main']['raw'];lines.append(f'| {name} | {t["passed"]} | {t["repaired"]} | {t["correct_controls_completed"]} | {t["false_DONE"]} | {t["abstained"]} |')
        summary[name]={part:brief(r[part]['raw'])for part in ['main','skills','goals','from_scratch','reproduction']}
    lines+=['','Успех — правильная программа, успешные обязательные публичные запуски и DONE. Отказ, преждевременный DONE и правильный код без завершения — провалы. Это raw-ответы сети: семантический порог не блокирует DONE. Эталонные значения и скрытые проверки используются только офлайн для оценки, агент их не получает.','',
      '| Вариант | Выбор операции/аргумента /288 | Ложных DONE | X²/X⁴ /192 | Ложных DONE | С нуля /64 | Старые ошибки /33 |','|---|---:|---:|---:|---:|---:|---:|']
    for name,r in all_results:
        s=r['skills']['raw'];g=r['goals']['raw'];f=r['from_scratch']['raw'];old=r['reproduction']['raw']
        lines.append(f'| {name} | {s["passed"]} | {s["false_DONE"]} | {g["passed"]} | {g["false_DONE"]} | {f["passed"]} | {old["passed"]} |')
    lines+=['',f'До открытия экзамена выбран **{selected}, блок {choice["block"]}**. Блок 0 — прежний balanced. Для каждой из трёх контрольных панелей новый кандидат должен сохранить число успехов и завершённых верных стартов, а также не увеличить ложные DONE. Только после этого сравнивается успех со штрафом 2 за ложный DONE и весами 0.60/0.25/0.15. Отдельное условие выпуска: ноль ложных DONE на всех панелях и ≥80% основного успеха. Оно выполнено: **{pre["release_eligible"]}**.','']
    if choice['block']==0:
        lines+=['Ни один новый чекпойнт не прошёл критерий продвижения лучше исходного balanced. В выбранный профиль сохранены прежние веса; успешное выполнение обучения не объявляется улучшением модели.','']
    old=initial['main']['raw'];new=results[selected]['main']['raw']
    lines += [f'На основном новом экзамене выбранный профиль: успех {old["passed"]} → {new["passed"]}, ложные DONE {old["false_DONE"]} → {new["false_DONE"]}, завершение верных стартов {old["correct_controls_completed"]} → {new["correct_controls_completed"]}.','']
    lines+=['Отдельная диагностика фиксированных последних весов после всех обновлений. Она показывает эффект SGD, даже если отбор сохранил блок 0. Эти веса не выбирались по экзамену и не подменяют профиль выше. Они экспортированы отдельно как replay-terminal/distill-terminal и также проверены нативно.','',
      '| Последний блок | Решено /480 | Ложных DONE | Завершено верных /240 | Пары /288 | Ложных DONE | X²/X⁴ /192 | Ложных DONE | С нуля /64 |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for arm,r in terminal.items():
        m,s,g,f=[r[k]['raw']for k in ['main','skills','goals','from_scratch']]
        lines.append(f'| {arm} | {m["passed"]} | {m["false_DONE"]} | {m["correct_controls_completed"]} | {s["passed"]} | {s["false_DONE"]} | {g["passed"]} | {g["false_DONE"]} | {f["passed"]} |')
    lines.append('')
    transitions={}
    for arm,r in terminal.items():
        transitions[arm]={}
        for part in ['main','skills','goals','from_scratch']:
            pairs=list(zip(initial[part]['raw']['details'],r[part]['raw']['details']))
            assert all(x['id']==y['id']for x,y in pairs)
            transitions[arm][part]={'gained':sum(not x['pass']and y['pass']for x,y in pairs),
              'lost':sum(x['pass']and not y['pass']for x,y in pairs),
              'new_false_DONE':sum(not(x['finished']and not x['program_correct'])and y['finished']and not y['program_correct']for x,y in pairs)}
    t=transitions['distill']['main']
    lines += [f'Попарное сравнение distill с исходным balanced на тех же основных эпизодах: {t["gained"]} новых успехов и {t["lost"]} потерянных успехов. Появились {t["new_false_DONE"]} ложных DONE на эпизодах, где исходный не выдавал ложный DONE. Улучшение суммарных показателей не означает сохранения каждого прежнего решения.','']
    regress=[]
    for part in ['main','skills','goals','from_scratch']:
        b=initial[part]['raw'];v=results[selected][part]['raw']
        if v['passed']<b['passed']or v['false_DONE']>b['false_DONE']or v['correct_controls_completed']<b['correct_controls_completed']:regress.append(part)
    if regress:lines+=['На новом экзамене остаются регрессии относительно исходного balanced: '+', '.join(regress)+'. Контрольный критерий не гарантирует отсутствие регрессий на других задачах.','']
    lines+=['Динамика контрольных наборов; отбор по raw, без семантического фильтра:','',
      '| Ветка | Блок | Основной успех | Ложных DONE | Пары: успех | Ложных DONE | X²/X⁴: успех | Ложных DONE | Все условия сохранения |','|---|---:|---:|---:|---:|---:|---:|---:|---|']
    development=load(root,'initial-development-audit.json')
    records=[('исходный',0,{k:development[k]['raw']for k in ['main','skills','goals']},True)]
    for block in range(1,policy['blocks']+1):
        values={arm:load(root,arm+f'/training-{block}.json')for arm in ARMS}
        assert values[ARMS[0]]['same_draw_digest']==values[ARMS[1]]['same_draw_digest']
        assert values[ARMS[0]]['counts']==values[ARMS[1]]['counts']
        for arm,v in values.items():records.append((arm,block,v['summary'],v['summary']['key'][0]))
    for arm,block,s,gate in records:
        m,p,g=[s[k]for k in ['main','skills','goals']]
        lines.append(f'| {arm} | {block} | {m["passed"]}/{m["total"]} | {m["false_DONE"]} | {p["passed"]}/{p["total"]} | {p["false_DONE"]} | {g["passed"]}/{g["total"]} | {g["false_DONE"]} | {gate} |')
    skills={t['id']:t for t in read(root/'fresh-skills.jsonl')}
    lines+=['','Результаты новых контрастных пар по семействам:','',
      '| Семейство | Исходный | replay | distill |','|---|---:|---:|---:|']
    for group in sorted({t['group']for t in skills.values()}):
        cells=[]
        for name,r in all_results:
            rows=[x for x in r['skills']['raw']['details']if skills[x['id']]['group']==group];cells.append(f'{sum(x["pass"]for x in rows)}/{len(rows)}')
        lines.append('| '+group+' | '+' | '.join(cells)+' |')
    lines+=['','Оценка правильности состояния (AUC, описательная метрика зависимых состояний): '+', '.join(f'{name} {auc(r["main"]["raw"]["calibration"]):.4f}'for name,r in all_results)+'.','']
    from ha_protocol import assemble
    from full_isa_vm import FullVM,check_task
    from tasks import save_jsonl
    task_lookup={t['id']:t for t in read(root/'fresh.jsonl')};vm=FullVM()
    def failures(report):
        rows=[]
        for seed,r in zip(read(root/'fresh-seeds.jsonl'),report['main']['raw']['details']):
            if not(r['finished']and not r['program_correct']):continue
            t=task_lookup[r['id']];code=assemble(r['body'],seed['pool'],'asm');checked=check_task(vm,code,t)
            bad=next((i for i,x in enumerate(checked['details'])if not x['pass']),None);failure=None
            if bad is not None:
                actual=checked['details'][bad]['segments'][0]['actual'];expected=(t['public_tests']+t['hidden_tests'])[bad]['segments'][0]['expected']
                failure={'case':bad,'public':bad<len(t['public_tests']),'actual_X':actual['numeric']['X'],'expected_X':expected['numeric']['X']}
            rows.append({'task_id':t['id'],'task':t['task'],'group':t['group'],'seed':seed,'initially_correct':r['initially_correct'],
              'body':r['body'],'wrong_code':code,'reference_code':t['reference_code'],'first_failure':failure,'history':r['history']})
        assert len(rows)==report['main']['raw']['false_DONE'];return rows
    remaining=failures(results[selected])
    assert len(remaining)==new['false_DONE']
    save_jsonl(root/'new-false-DONE.jsonl',remaining)
    lines += [f'Оставшиеся {len(remaining)} ложных DONE сохранены с задачей, кодом, эталоном и полным протоколом в [new-false-DONE.jsonl]('+str(root/'new-false-DONE.jsonl')+').','']
    terminal_remaining={arm:failures(r)for arm,r in terminal.items()}
    for arm,rows in terminal_remaining.items():
        file=root/f'terminal-false-DONE-{arm}.jsonl';save_jsonl(file,rows)
        lines.append(f'Итоговые новые веса {arm}: {len(rows)} ложных DONE, [полные воспроизведения]({file}).')
        losses=[]
        for seed,old_row,new_row in zip(read(root/'fresh-seeds.jsonl'),initial['main']['raw']['details'],terminal[arm]['main']['raw']['details']):
            if old_row['pass']and not new_row['pass']:
                losses.append({'task_id':new_row['id'],'task':task_lookup[new_row['id']]['task'],'seed':seed,'baseline':old_row,'terminal':new_row})
        file=root/f'terminal-retention-regressions-{arm}.jsonl';save_jsonl(file,losses)
        lines.append(f'Потерянные относительно исходного успехи {arm}: {len(losses)}, [полные воспроизведения]({file}).')
    lines+=['','Примеры оставшихся ошибок новой distill:','']
    seen=set()
    for r in terminal_remaining['distill']:
        if r['task_id']in seen:continue
        seen.add(r['task_id']);f=r['first_failure'];wrong=' '.join(f'{x:02X}'for x in r['wrong_code'])
        lines.append(f'- {r["task"]} Ответ HEX: `{wrong}`.'+(f' На проверке X={f["actual_X"]}, ожидалось {f["expected_X"]}.'if f else''))
        if len(seen)==10:break
    lines+=['','Проверка прежних пользовательских формулировок (уже виденные при обучении):','',
      '| Запрос | replay | distill | Нативный выбранный |','|---|---|---|---|']
    for i,r in enumerate(demos[ARMS[0]]['raw']):lines.append('| '+r['task']+' | '+' | '.join('решено'if demos[arm]['raw'][i]['pass']else'не решено'for arm in [*ARMS,'native-selected'])+' |')
    lines.append('')
    for arm,d in demos.items():lines.append(f'- {arm}: верные контрольные программы {sum(r["pass"]for r in d["already_correct"])}/{len(d["already_correct"])}; неполное условие → UNSURE {d["unknown_correct"]}/{len(d["unknown"])}.')
    lines+=['','Q4 и нативное исполнение:','']
    for arm,r in native['models'].items():
        lines.append(f'- {arm}: точная повторная упаковка/загрузка; CPU/B200 {r["cpu_matches"]}/{r["probes"]}, C++/B200 {r["native_matches"]}/{r["probes"]}; MKA {r["package_bytes"]:,} байт.')
        if arm!='compiler':lines.append(f'  Максимальная ошибка margin {max(x["margin_error"]for x in r["details"]):.6g}; пороговые решения совпали {r["threshold_decisions_matched"]}/{r["probes"]}.')
    mem=native['models'][selected];long=native['long_input_regression']
    lines += [f'- Общий буфер весов {native["shared_weight_buffer_bytes"]:,} байт; FP32 KV {mem["cache_bytes"]:,} байт на 1024 токена; workspace {mem["workspace_bytes"]:,} байт; вспомогательные логиты 32 896 байт. Переключение компилятор → отладчик → компилятор проверено.',
      f'- Ввод до {long["input_byte_limit"]} UTF-8 байт; проверено {long["prefixes_checked"]} длинных префиксов, до {long["max_utf8_bytes_checked"]} байт. Переполнение байтов и контекста отклоняется.',
      '- Физический PicoCalc не измерялся. Исходники прошивки не изменены. Родительские модели, исходники и корпус проверены по хешам; собственные GPU-задания завершены.','',
      'Локальный runner: [ah_chat.py]('+str(HERE/'ah_chat.py')+'), raw по умолчанию. Он принимает русский запрос, угол, открытые входы и необязательный исходный HEX. DONE остаётся решением сети, а не доказательством правильности.']
    path=HERE/'RETENTION_DEBUG_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    result={'completed':True,'selected_arm':selected,'selected_block':choice['block'],'optimizer_updates':updates,'release_eligible':pre['release_eligible'],
      'baseline':summary['Исходный balanced'],'results':{k:v for k,v in summary.items()if k!='Исходный balanced'},'fresh_regression_panels':regress,
      'native_verification_complete':native['complete'],'physical_device_measured':False,'new_checkpoint_promoted':choice['block']>0,
      'terminal_diagnostics':{arm:{k:brief(r[k]['raw'])for k in ['main','skills','goals','from_scratch']}for arm,r in terminal.items()},
      'paired_terminal_transitions':transitions,
      'verified_old_anchors':data['anchors'],'teacher_no_gradients_verified':prepared['frozen_teacher_unchanged_and_no_gradients']}
    write(root/'summary.json',result);state_path=HERE/'work-state.json';state=json.loads(state_path.read_text())
    if not state.get('retention_debug_v1',{}).get('completed'):
        state['completed_training_runs']=state.get('completed_training_runs',70)+2
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',265958)+updates
    state.update(phase='retention_debug_v1_complete',all_own_jobs_complete=True,active_experiment=None,next_action='Review retention/Q4 results and remaining failures; no firmware deployment requested.')
    state['retention_debug_v1']={'completed':True,'report':str(path),'root':str(root),'summary':result};write(state_path,state)
    print(json.dumps({'completed':True,'report':str(path),'selected_arm':selected,'selected_block':choice['block'],'release_eligible':pre['release_eligible']}),flush=True)


if __name__=='__main__':main()
