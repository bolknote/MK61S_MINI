"""Report a short continuation from distill without hiding retention failures."""
import argparse
import collections
import json
from pathlib import Path
from ai_common import HERE,ARMS,PANELS,read,write
from ae_report import brief


def load(root,name):return json.loads((root/name).read_text())


def transitions(old,new):
    pairs=list(zip(old['details'],new['details']))
    assert len(old['details'])==len(new['details'])and all(a['id']==b['id']for a,b in pairs)
    return{'gained':sum(not a['pass']and b['pass']for a,b in pairs),'lost':sum(a['pass']and not b['pass']for a,b in pairs),
      'new_false_DONE':sum(not(a['finished']and not a['program_correct'])and b['finished']and not b['program_correct']for a,b in pairs)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    pre=load(root,'preselected.json');policy=load(root,'policy.json');data=load(root,'data-frozen.json');prepared=load(root,'prepared.json')
    initial=load(root,'initial-fresh-audit.json');results={arm:load(root,arm+'-fresh-audit.json')for arm in ARMS}
    terminal={arm:load(root,arm+'/terminal-fresh-audit.json')for arm in ARMS};native=load(root,'native-verification.json')
    demos=load(root,'user-reproductions.json');selected=pre['selected_arm'];choice=pre['choices'][selected]
    updates=len(ARMS)*policy['blocks']*policy['steps_per_block'];names=[n for n,_,_ in PANELS];all_parts=names+['from_scratch','reproduction']
    before=initial['main']['raw'];after=results[selected]['main']['raw'];cp=transitions(before,after)
    lines=['# 3M Q4: завершение программ и удержание навыков','',
      f'На новом основном экзамене выбранный профиль: успех {before["passed"]} → {after["passed"]} из {before["total"]}, ложные DONE {before["false_DONE"]} → {after["false_DONE"]}. Выбран до экзамена: **{selected}, блок {choice["block"]}**, то есть {choice["block"]*policy["steps_per_block"]} новых обновлений. Условие выпуска выполнено: **{pre["release_eligible"]}**.','',
      'Отправная точка — итоговые веса distill предыдущего retention-debug-v1, блок 3. Обе ветки продолжают те же LoRA rank16/alpha32; после слияния каждый профиль содержит 3 022 080 параметров Q4. LR20 использует базовую скорость 2×10⁻⁵, LR10 — 1×10⁻⁵. Данные, выборки, потери и два замороженных учителя у них одинаковы.','',
      f'Выполнены {policy["blocks"]} × {policy["steps_per_block"]} обновлений каждой ветки, всего **{updates}**. Контроль проводится каждые 250 обновлений. Текущие ошибки обеих веток объединяются в проверенный учебный набор после блоков 2 и 4. В каждом прямом проходе адаптируемые матрицы находятся на сетке реального Q4.','',
      f'Данные: {data["task_counts"]["new_train"]} новых задач, {data["lessons"]:,} обычных шагов, {data["hard_lessons"]:,} шагов из реальных ошибок и проверенных продолжений, {data["completion_lessons"]:,} шагов завершения после повторных WRITE; {data["retention_lessons"]:,} прежних шагов. Прежние 40 ложных DONE и 28 потерь дедуплицированы в {data["reproduction_episodes"]} учебных эпизодов.','',
      f'Для удержания навыков отобраны {data["anchors"]} решений: 2815 от balanced и 1584 от исходного distill. Каждое действие взято из успешного эпизода и дополнительно согласовано с ROM-экспертом. Неверные WRITE/DONE не копируются. Прежний экзамен теперь является обучением. Новых вызовов большой LLM не было.','',
      'Учебный батч из 64 строк содержит реальные ошибки, состояния самого ученика, завершение верного кода, новые составные задачи, контрастные пары и сохранение прежних решений. Дополнительно по 8 подтверждённых состояний каждого учителя удерживают распределения пяти действий и 23 токенов HEX-тела: температура 2, общий вес KL 2.','',
      'Для ROM-правильного состояния, где следующий допустимый шаг — RUN или DONE, добавлена потеря с отступом 1 и весом 0.2 против ненужных WRITE/UNSURE. Неверная программа и состояние с недостаточным бюджетом проверок этим слагаемым к DONE не подталкиваются. Учитель размечает полные исправляющие продолжения в пределах оставшихся действий.','',
      'До SGD зафиксированы новые контроль и экзамен. Точные тексты не пересекаются с обучением и прежними наборами; проверяются новые формулировки/экземпляры знакомых семейств. Дополнительная панель завершения начинает с правильного кода после 2, 4 или 6 повторных записей; они расходуют бюджет действий, часть публичных тестов может ещё требовать RUN.','',
      '| Профиль по контролю | Решено /480 | Исправлено /240 | Завершено верных /240 | Ложных DONE | UNSURE |','|---|---:|---:|---:|---:|---:|']
    all_results=[('Исходный distill',initial),*results.items()]
    for name,r in all_results:
        m=r['main']['raw'];lines.append(f'| {name} | {m["passed"]} | {m["repaired"]} | {m["correct_controls_completed"]} | {m["false_DONE"]} | {m["abstained"]} |')
    lines+=['','| Профиль | Операции/аргументы /288 | Ложных DONE | X²/X⁴ /192 | Ложных DONE | Выход из WRITE /144 | Ложных DONE | С нуля /64 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,r in all_results:
        s,g,c,f=[r[k]['raw']for k in ['skills','goals','completion','from_scratch']]
        lines.append(f'| {name} | {s["passed"]} | {s["false_DONE"]} | {g["passed"]} | {g["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} | {f["passed"]} |')
    lines+=['','Успех требует верного кода, успешного исполнения всех обязательных публичных случаев и DONE. Правильный незавершённый код, отказ и преждевременный DONE не считаются успехом. Это raw-ответы сети: семантический порог не блокирует DONE. Скрытые проверки, эталонный код и ожидаемые значения доступны только офлайн-оценке.','',
      'Отбор: на каждой из четырёх контрольных панелей число успехов и завершённых верных стартов должно быть не ниже исходного distill, а ложных DONE — не больше. Затем сравнивается (успех − 2×ложные DONE)/размер с весами 0.50/0.20/0.15/0.15. Исходные веса включены как блок 0. Условие выпуска отдельно требует ноль ложных DONE на всех панелях и ≥80% основного успеха. Экзамен не меняет веса, пороги или выбор.','']
    if choice['block']==0:lines+=['Новый чекпойнт не прошёл правило продвижения. Выбранный профиль сохраняет исходный distill; ниже отдельно приведён эффект всех новых обновлений.','']
    lines += [f'На тех же основных эпизодах у выбранного профиля {cp["gained"]} приобретённых успехов и {cp["lost"]} потерянных.','',
      '| Фиксированные последние веса | Решено /480 | Ложных DONE | Операции /288 | X²/X⁴ /192 | Выход из WRITE /144 | С нуля /64 |','|---|---:|---:|---:|---:|---:|---:|']
    for arm,r in terminal.items():
        m,s,g,c,f=[r[k]['raw']for k in ['main','skills','goals','completion','from_scratch']]
        lines.append(f'| {arm}-terminal | {m["passed"]} | {m["false_DONE"]} | {s["passed"]} | {g["passed"]} | {c["passed"]} | {f["passed"]} |')
    lines+=['','Последние веса — заранее определённый блок 6, отдельная диагностика. Они не подменяют отбор по контролю. Для них также сохранены HF/MKQB/MKA и проверено нативное исполнение.','',
      '| Контроль | Блок | Основной успех /320 | Ложных DONE | Пары /192 | X²/X⁴ /128 | Завершение /96 | Все условия удержания |','|---|---:|---:|---:|---:|---:|---:|---|']
    baseline=load(root,'initial-development-audit.json')
    b=[baseline[n]['raw']for n in names];lines.append(f'| исходный | 0 | {b[0]["passed"]} | {b[0]["false_DONE"]} | {b[1]["passed"]} | {b[2]["passed"]} | {b[3]["passed"]} | True |')
    for block in range(1,policy['blocks']+1):
        values={arm:load(root,arm+f'/training-{block}.json')for arm in ARMS}
        assert values[ARMS[0]]['same_draw_digest']==values[ARMS[1]]['same_draw_digest']and values[ARMS[0]]['counts']==values[ARMS[1]]['counts']
        for arm,v in values.items():
            p=[v['summary'][n]for n in names]
            lines.append(f'| {arm} | {block} | {p[0]["passed"]} | {p[0]["false_DONE"]} | {p[1]["passed"]} | {p[2]["passed"]} | {p[3]["passed"]} | {v["summary"]["key"][0]} |')
    lines+=['','| Прежние учебные ошибки | Правильно завершено | Ложных DONE |','|---|---:|---:|']
    for name,r in all_results:
        p=r['reproduction']['raw'];lines.append(f'| {name} | {p["passed"]}/{p["total"]} | {p["false_DONE"]} |')
    from full_isa_vm import FullVM,check_task
    from ha_protocol import assemble
    from tasks import save_jsonl
    vm=FullVM();lookup={t['id']:t for t in read(root/'fresh.jsonl')};seeds=read(root/'fresh-seeds.jsonl')
    def failures(report):
        rows=[]
        for seed,r in zip(seeds,report['main']['raw']['details']):
            if not(r['finished']and not r['program_correct']):continue
            t=lookup[r['id']];code=assemble(r['body'],seed['pool'],'asm');checked=check_task(vm,code,t);first=None
            bad=next((i for i,c in enumerate(checked['details'])if not c['pass']),None)
            if bad is not None:
                actual=checked['details'][bad]['segments'][0]['actual'];expected=(t['public_tests']+t['hidden_tests'])[bad]['segments'][0]['expected']
                first={'case':bad,'public':bad<len(t['public_tests']),'actual_X':actual['numeric']['X'],'expected_X':expected['numeric']['X']}
            rows.append({'task_id':t['id'],'task':t['task'],'group':t['group'],'seed':seed,'initially_correct':r['initially_correct'],
              'body':r['body'],'wrong_code':code,'reference_code':t['reference_code'],'first_failure':first,'history':r['history']})
        assert len(rows)==report['main']['raw']['false_DONE'];return rows
    reports={'selected':results[selected],**{arm+'-terminal':r for arm,r in terminal.items()}};paired={}
    lines+=['','Оставшиеся ошибки и регрессии:','']
    for name,r in reports.items():
        wrong=failures(r);file=root/('new-false-DONE.jsonl'if name=='selected'else f'false-DONE-{name}.jsonl');save_jsonl(file,wrong)
        paired[name]={part:transitions(initial[part]['raw'],r[part]['raw'])for part in names+['from_scratch']}
        lost=[{'task_id':n['id'],'task':lookup[n['id']]['task'],'seed':seed,'baseline':b,'terminal':n}
          for seed,b,n in zip(seeds,initial['main']['raw']['details'],r['main']['raw']['details'])if b['pass']and not n['pass']]
        regression=root/f'retention-regressions-{name}.jsonl';save_jsonl(regression,lost)
        lines.append(f'- {name}: {len(wrong)} ложных DONE, [воспроизведения]({file}); {len(lost)} потерянных успехов, [разбор]({regression}).')
    lines+=['','Примеры ложных DONE выбранного профиля:',''];seen=set()
    for r in failures(results[selected]):
        if r['task_id']in seen:continue
        seen.add(r['task_id']);f=r['first_failure'];code=' '.join(f'{x:02X}'for x in r['wrong_code'])
        lines.append(f'- {r["task"]} HEX: `{code}`.'+(f' Получено X={f["actual_X"]}, ожидалось {f["expected_X"]}.'if f else''))
        if len(seen)==10:break
    lines+=['','Проверка прежних пользовательских формулировок, уже виденных при обучении:','',
      '| Запрос | lr20 | lr10 | Нативный выбранный |','|---|---|---|---|']
    for i,r in enumerate(demos[ARMS[0]]['raw']):lines.append('| '+r['task']+' | '+' | '.join('решено'if demos[arm]['raw'][i]['pass']else'не решено'for arm in [*ARMS,'native-selected'])+' |')
    lines.append('')
    for arm,d in demos.items():lines.append(f'- {arm}: правильные контрольные программы {sum(r["pass"]for r in d["already_correct"])}/{len(d["already_correct"])}; неполное условие → UNSURE {d["unknown_correct"]}/{len(d["unknown"])}.')
    lines+=['','Q4 и нативное исполнение:','']
    for arm,p in native['models'].items():
        lines.append(f'- {arm}: точная упаковка/загрузка Q4; CPU/B200 {p["cpu_matches"]}/{p["probes"]}, C++/B200 {p["native_matches"]}/{p["probes"]}; MKA {p["package_bytes"]:,} байт.')
        if arm!='compiler':lines.append(f'  Максимальная ошибка margin {max(x["margin_error"]for x in p["details"]):.6g}; пороговые решения совпали {p["threshold_decisions_matched"]}/{p["probes"]}.')
    mem=native['models'][selected];long=native['long_input_regression']
    lines += [f'- Общий буфер весов {native["shared_weight_buffer_bytes"]:,} байт; KV {mem["cache_bytes"]:,} байт на 1024 токена; workspace {mem["workspace_bytes"]:,} байт; вспомогательные логиты 32 896 байт.',
      f'- Проверены переключения профилей, {long["prefixes_checked"]} длинных префиксов и отклонение переполнения ввода/контекста. Предельный ввод {long["input_byte_limit"]} UTF-8 байт.',
      '- Прямой проход перед SGD побитово согласован с экспортом; оба учителя заморожены, входные строки не изменяются. Корпус, учебные исходники, родительские модели и приватное ядро проверены по хешам. Все собственные задания закончены.',
      '- Физический PicoCalc не измерялся, прошивка не изменялась.','',
      'Локальный runner: [ai_chat.py]('+str(HERE/'ai_chat.py')+'). Режим raw по умолчанию; поддерживает профили lr20, lr10, их terminal-варианты и selected-research. Заявление DONE остаётся решением модели.']
    path=HERE/'COMPLETION_RETENTION_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    summary={'completed':True,'selected_arm':selected,'selected_block':choice['block'],'new_checkpoint_promoted':choice['block']>0,
      'optimizer_updates':updates,'release_eligible':pre['release_eligible'],'baseline':{n:brief(initial[n]['raw'])for n in all_parts},
      'results':{arm:{n:brief(r[n]['raw'])for n in all_parts}for arm,r in results.items()},
      'terminal_diagnostics':{arm:{n:brief(r[n]['raw'])for n in names+['from_scratch']}for arm,r in terminal.items()},
      'paired_transitions':paired,'verified_anchors':data['anchors'],'frozen_teachers_verified':prepared['frozen_teacher_unchanged_and_no_gradients'],
      'native_verification_complete':native['complete'],'physical_device_measured':False}
    write(root/'summary.json',summary);state_path=HERE/'work-state.json';state=load(HERE,'work-state.json')
    if not state.get('completion_retention_v1',{}).get('completed'):
        state['completed_training_runs']=state.get('completed_training_runs',72)+len(ARMS)
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',271958)+updates
    state.update(phase='completion_retention_v1_complete',all_own_jobs_complete=True,active_experiment=None,
      next_action='Review completion/retention Q4 results and remaining errors; no firmware deployment requested.',latest_report=str(path))
    state['completion_retention_v1']={'completed':True,'report':str(path),'root':str(root),'summary':summary};write(state_path,state)
    print(json.dumps({'completed':True,'report':str(path),'selected_arm':selected,'selected_block':choice['block'],'release_eligible':pre['release_eligible']}),flush=True)


if __name__=='__main__':main()
