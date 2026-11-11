"""Report learned completion separately from an external semantic DONE filter."""
import argparse
import json
from af_common import HERE,ARMS,read,write
from ae_report import auc,brief


def subgroup(panel,ids):
    rows=[r for r in panel['details']if r['id']in ids]
    return {'total':len(rows),'passed':sum(r['pass']for r in rows),
      'false_DONE':sum(r['finished']and not r['program_correct']for r in rows),
      'repaired':sum(r['pass']and not r['initially_correct']for r in rows),
      'wrong_starts':sum(not r['initially_correct']for r in rows)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True,type=__import__('pathlib').Path);a=ap.parse_args();root=a.root.resolve()
    pre=json.loads((root/'preselected.json').read_text());data=json.loads((root/'data-frozen.json').read_text());policy=json.loads((root/'policy.json').read_text())
    baseline=json.loads((root/'initial-fresh-audit.json').read_text());results={arm:json.loads((root/(arm+'-fresh-audit.json')).read_text())for arm in ARMS}
    native=json.loads((root/'native-verification.json').read_text());demos=json.loads((root/'user-reproductions.json').read_text())
    updates=len(ARMS)*policy['blocks']*policy['steps_per_block'];tasks=read(root/'fresh.jsonl');summary={}
    lines=['# 3M Q4: X²/X⁴, завершение верного кода и ложные DONE','',
      'Завершено продолжение прежнего выбранного LoRA rank16 на двух B200. Исходная точка — существующие факторы адаптера lora16, блок 2 предыдущего semantic-debug-v2. Они продолжают обучаться поверх прежнего неизменённого Q4-основания; новый адаптер с нуля не создавался. Компилятор сохранён отдельным профилем.','',
      f'Обучение: две ветки, по {policy["blocks"]} × {policy["steps_per_block"]} обновлений; всего **{updates}**. Replay получает адресное SFT, отдельную оценку правильности и штраф ложного DONE. Contrast дополнительно ранжирует пары по семантическому баллу и вероятности DONE. Основные учебные выборки и случайные пары совпадают между ветками; контрольные суммы сверены после каждого блока. Начальная точка включена в выбор лучшего чекпойнта, поэтому ухудшение всех блоков сохраняет блок 0.','',
      f'Корпус: {data["task_counts"]["train"]} задач, {data["lessons"]:,} адресных размеченных состояний, {data["pairs"]:,} контрастных пар; отдельно {data["retention_lessons"]:,} прежних шагов для сохранения навыков всех документированных команд. В адресной части {data["replayed_student_states"]:,} фактических состояний предыдущих учеников, включая {data["prior_false_DONE_states"]} неверных DONE и {data["prior_unnecessary_WRITE_states"]} записей при уже правильном коде. Прежний просмотренный экзамен теперь явно включён в обучение.','',
      'Добавлены близкие программы X²/X⁴/X⁸, квадрат суммы с константой и ввод точных констант, включая 0. Правильные программы размечаются DONE после всех успешных публичных запусков, в том числе после повторных записей и на разных остатках бюджета действий. Для неверного кода учитель даёт проверенное исправление. Вторая группа пар имеет одинаковые код, входы и наблюдения, но противоположные цели X²/X⁴. Константы иногда переставлены согласованно со ссылками.','',
      'Учитель — авторские эталонные программы с проверкой реальным ROM и явных требований. Новых вызовов большой LLM не было. Эталон, ожидаемые значения и скрытые проверки не поступают в запросы модели или обратную связь эмулятора. Контекст, действия и формат HEX/FF не менялись.','',
      'До первого обновления найдено расхождение округления CUDA и CPU у границ нескольких групп Q4. В новом адаптере деление для округления согласовано с CPU-экспортом, а прямой проход STE возвращает точное значение сетки. Проверка подтвердила побитовое равенство всех адаптируемых матриц экспорту, прежний стартовый пакет остался прежним; команды и вспомогательные баллы на стартовых пробах совпали без расхождения. Предварительные попытки не выполняли обновлений оптимизатора. Старые эксперименты и их исходники не менялись.','',
      'Новый контроль и экзамен зафиксированы до SGD. Совпадения точного текста с более ранними наборами заменены до обучения. Основной экзамен: 240 новых задач × правильный/ошибочный старт = 480 эпизодов; отдельные пары X²/X⁴ содержат 48 задач и 192 эпизода. Это новые формулировки и экземпляры знакомых семейств, а не полностью новые классы программ. Экзамен не выбирает веса, порог или гиперпараметры.','',
      '| Вариант | Режим | Решено /480 | Исправлено /240 | Завершено верных стартов /240 | Ложных DONE | UNSURE |',
      '|---|---|---:|---:|---:|---:|---:|']
    for name,r in [('Исходный адаптер',baseline),*results.items()]:
        for mode,t in r['main'].items():
            lines.append(f'| {name} | {mode} | {t["passed"]} | {t["repaired"]} | {t["correct_controls_completed"]} | {t["false_DONE"]} | {t["abstained"]} |')
            summary.setdefault(name,{})[mode]=brief(t)
    lines+=['','Raw — решения самой сети без запрета DONE внешней головкой. Успех требует верной программы, DONE и всех успешных публичных запусков. Calibrated отдельно накладывает порог семантической головки, выбранный на контроле выше любого ошибочного состояния. Этот диагностический режим не выбирает лучший профиль и не заменяет проверку raw. Отказ подтвердить правильный результат считается неуспехом.','',
      '| Вариант | X²/X⁴: решено /192 | Исправлено /96 | Завершено верных стартов /96 | Ложных DONE | С нуля /64 |',
      '|---|---:|---:|---:|---:|---:|']
    premature={name:r['main']['raw']['premature_DONE']for name,r in [('Исходный адаптер',baseline),*results.items()]}
    lines[-4:-4]=['','Ложный DONE в таблице означает неверную программу. Отдельно считаются преждевременные DONE без всех успешных публичных запусков: '+', '.join(f'{name}: {n}'for name,n in premature.items())+'. Они также не считаются успехом.','']
    for name,r in [('Исходный адаптер',baseline),*results.items()]:
        g=r['goals']['raw'];s=r['from_scratch']['raw']
        lines.append(f'| {name} | {g["passed"]} | {g["repaired"]} | {g["correct_controls_completed"]} | {g["false_DONE"]} | {s["passed"]} |')
    lines+=['','Разбор основного raw-экзамена:','','| Группа | Исходный адаптер | replay | contrast |','|---|---:|---:|---:|']
    groups=[('Простые',{t['id']for t in tasks if t['level']==1}),('Составные',{t['id']for t in tasks if t['level']==2}),('Сложные',{t['id']for t in tasks if t['level']==3})]
    groups += [(name,{t['id']for t in tasks if t.get('group')==key})for name,key in [('Близкие степени','power_near_miss'),('Завершение констант','literal_completion'),('Квадрат суммы','shifted_square')]]
    for name,ids in groups:
        values=[subgroup(r['main']['raw'],ids)for r in [baseline,*results.values()]]
        lines.append('| '+name+' | '+' | '.join(f'{x["passed"]}/{x["total"]}'for x in values)+' |')
    lines+=['','Контрольная динамика (320 основных эпизодов, 128 эпизодов смены цели):','',
      '| Ветка | Блок | Решено | Ложных DONE | X²/X⁴ решено | X²/X⁴ ложных DONE |','|---|---:|---:|---:|---:|---:|']
    for block in range(1,policy['blocks']+1):
        values={arm:json.loads((root/arm/f'training-{block}.json').read_text())for arm in ARMS}
        assert values[ARMS[0]]['same_draw_digest']==values[ARMS[1]]['same_draw_digest']
        assert values[ARMS[0]]['counts']==values[ARMS[1]]['counts']
        for arm,v in values.items():
            m=v['summary']['main'];g=v['summary']['goals'];lines.append(f'| {arm} | {block} | {m["passed"]} | {m["false_DONE"]} | {g["passed"]} | {g["false_DONE"]} |')
    selected=pre['selected_arm'];choice=pre['choices'][selected];start=baseline['main']['raw'];chosen=results[selected]['main']['raw']
    lines+=['',f'Выбрано до экзамена: **{selected}, блок {choice["block"]}**. Критерий: сначала достижение 0 ложных DONE на обеих контрольных панелях при ≥80% успеха основной, затем взвешенный успех со штрафом 2 за ложный DONE. Пройденный критерий выпуска: **{pre["release_eligible"]}**. Ноль наблюдённых ошибок на конечном наборе не доказывает отсутствие ошибок вообще.','',
      '| Ветка | Порог (только контроль) | AUC на посещённых новых состояниях |','|---|---:|---:|']
    for arm,r in results.items():lines.append(f'| {arm} | {r["threshold"]:.6f} | {auc(r["main"]["raw"]["calibration"]):.4f} |')
    lines+=['','AUC описывает ранжирование посещённых состояний; состояния одной задачи зависимы.','',
      'Оставшиеся ложные DONE выбранного raw-профиля (до трёх примеров; эталон показан только при офлайн-разборе после экзамена):','']
    from ha_protocol import assemble
    lookup={t['id']:t for t in tasks};failures=0
    for seed,r in zip(read(root/'fresh-seeds.jsonl'),chosen['details']):
        if not r['finished']or r['program_correct']:continue
        t=lookup[r['id']];code=assemble(r['body'],seed['pool'],'asm')
        lines += ['- '+t['task'],'  Выдано: `'+bytes(code).hex(' ').upper()+'`; эталон: `'+bytes(t['reference_code']).hex(' ').upper()+'`.']
        failures+=1
        if failures==3:break
    if not failures:lines.append('На основном новом экзамене таких примеров нет.')
    lines+=['','Повторение четырёх пользовательских ошибок (они включены в адресное обучение; это воспроизведение, не новый экзамен):','',
      '| Запрос | replay raw | contrast raw | Нативный выбранный raw |','|---|---|---|---|']
    for i,r in enumerate(demos[ARMS[0]]['raw']):
        lines.append('| '+r['task']+' | '+' | '.join('решено'if demos[arm]['raw'][i]['pass']else'не решено'for arm in [*ARMS,'native-selected'])+' |')
    lines.append('')
    for arm,d in demos.items():
        lines.append(f'- Уже верные версии этих программ, включая повторную запись: {arm} {sum(r["pass"]for r in d["already_correct"])}/{len(d["already_correct"])}; неполные условия: UNSURE {d["unknown_correct"]}/{len(d["unknown"])}.')
    manual=[]
    for name,title in [('square','X² вместо ошибочного X⁴'),('fourth','X⁴ вместо ошибочного X²'),('zero','0 вместо ошибочной константы 1')]:
        p=root.parent/('manual-'+name+'.jsonl')
        if not p.exists():continue
        records=[json.loads(line)for line in p.read_text().splitlines()];last=records[-1];actual={}
        for r in records:
            if r.get('kind')in ['write','run']:
                value=json.loads(r['observation']);actual[value['case']]=value['actual'][-1]['X']
        manual.append('- '+title+': `'+bytes(last['program']).hex(' ').upper()+'`; X для входов 2.5, −3, 0: '+', '.join(actual[k]for k in sorted(actual))+f'; DONE={last["model_declared_done"]}. [Протокол]('+str(p)+').')
    if manual:lines+=['','Дополнительные ручные прогоны нативного выбранного Q4 на трёх открытых входах:', '',*manual]
    lines+=['','Нативная проверка и размер:','']
    for arm,r in native['models'].items():
        lines.append(f'- {arm}: точная повторная упаковка и загрузка Q4; CPU/B200 {r["cpu_matches"]}/{r["probes"]}, C++/B200 {r["native_matches"]}/{r["probes"]}; файл MKA {r["package_bytes"]:,} байт.')
        if arm!='compiler':lines.append(f'  Пороговые решения совпали {r["threshold_decisions_matched"]}/{r["probes"]}; максимальное расхождение margin {max(x["margin_error"]for x in r["details"]):.6g}.')
    lines+=['- Каждый профиль по-прежнему 3 022 080 параметров Q4. Входные русские embedding-строки побитово сохранены, кроме служебных выходных строк; LoRA сливается в исходные матрицы. Дополнительного адаптера при исполнении нет.',
      f'- Весовой буфер 2 160 856 байт, FP32 KV-кеш на 1024 токена 5 242 880 байт, рабочая память ядра {native["models"][selected]["workspace_bytes"]:,} байт и временные логиты 32 896 байт. Компилятор → отладчик → компилятор переключаются в одном буфере. Полный пик интерфейса/эмулятора и скорость физического PicoCalc не измерены.',
      f'- В частной исследовательской копии исправлен унаследованный предел 2048 UTF-8 байт: он отказывал на запросе в 797 токенов/2059 байт. Лимит текста теперь {native["long_input_regression"]["input_byte_limit"]} байт, сегментный буфер стека {native["long_input_regression"]["segment_stack_buffer_bytes"]} байт. Токенизация {native["long_input_regression"]["prefixes_checked"]} длинных запросов совпала с HF, проверено до {native["long_input_regression"]["max_utf8_bytes_checked"]} байт; превышение байтового лимита и контекста отвергается. Исходники прошивки не менялись.','',
      f'Итог выбранной ветки на новом raw-экзамене: {start["passed"]} → {chosen["passed"]} правильных завершений, {start["false_DONE"]} → {chosen["false_DONE"]} ложных DONE. Внешний фильтр следует оценивать отдельно по числу полезных завершений; он не превращает оценку сети в доказательство. Все собственные GPU-задания завершены, исходные файлы и родительский адаптер проверены по хешам.','',
      'Подготовлен локальный [af_chat.py]('+str(HERE/'af_chat.py')+'), по умолчанию raw. Поддерживает --native, русский запрос, угол, публичные входы и --initial-hex. Его model_declared_done является заявлением модели; verified_task_success остаётся null без доверенного эталона. В прошивку профиль не устанавливался.']
    path=HERE/'FINISH_DEBUG_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    result={'completed':True,'selected_arm':selected,'selected_block':choice['block'],'release_eligible':pre['release_eligible'],
      'optimizer_updates':updates,'baseline':brief(start),'results':summary,'native_verification_complete':native['complete'],'physical_device_measured':False}
    write(root/'summary.json',result);state_path=HERE/'work-state.json';state=json.loads(state_path.read_text())
    if not state.get('finish_debug_v1',{}).get('completed'):
        state['completed_training_runs']=state.get('completed_training_runs',66)+2
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',250758)+updates
    state.update(phase='finish_debug_v1_complete',all_own_jobs_complete=True,active_experiment=None,next_action='Review final adapter results; no firmware deployment requested.')
    state['finish_debug_v1']={'completed':True,'report':str(path),'root':str(root),'summary':result};write(state_path,state)
    print(json.dumps({'completed':True,'report':str(path),'selected_arm':selected,'release_eligible':pre['release_eligible']}),flush=True)


if __name__=='__main__':main()
