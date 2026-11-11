"""Separate replay of the forty training failures from genuinely new tasks."""
import argparse
import json
from pathlib import Path
from ag_common import HERE,ARMS,read,write
from ae_report import auc,brief
from ag_analyze import LABELS


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    pre=json.loads((root/'preselected.json').read_text());data=json.loads((root/'data-frozen.json').read_text());policy=json.loads((root/'policy.json').read_text())
    analysis=json.loads((root/'forty-analysis.json').read_text());native=json.loads((root/'native-verification.json').read_text());demos=json.loads((root/'user-reproductions.json').read_text())
    initial=json.loads((root/'initial-fresh-audit.json').read_text());results={arm:json.loads((root/(arm+'-fresh-audit.json')).read_text())for arm in ARMS}
    selected=pre['selected_arm'];choice=pre['choices'][selected];updates=len(ARMS)*policy['blocks']*policy['steps_per_block'];summary={}
    lines=['# Дообучение 3M Q4 на оставшихся 40 ложных DONE','',
      'Продолжены существующие LoRA rank16-факторы выбранного replay-адаптера finish-debug-v1, блок 4. Основание и компилятор сохранены. Архитектура, русский входной словарь, команды и HEX/FF-протокол не расширялись. После слияния каждый профиль по-прежнему содержит 3 022 080 параметров Q4.','',
      'Полный разбор сорока исходных эпизодов: [FORTY_FALSE_DONE_ANALYSIS.md]('+str(HERE/'FORTY_FALSE_DONE_ANALYSIS.md')+').','',
      '| Причина | Эпизодов |','|---|---:|',*[f'| {LABELS[k]} | {v} |'for k,v in analysis['categories'].items()], '',
      f'Всего {analysis["episodes"]} эпизодов и {analysis["distinct_tasks"]} разных задач. В {analysis["correct_starts_broken"]} случаях сеть испортила верный старт. В {analysis["no_attempted_WRITE"]} не пыталась переписать код. Все {analysis["publicly_observable_failures"]} провалов воспроизведены уже на публичных входах при офлайн-сравнении с эталоном; скрытых-only ошибок {analysis["hidden_only_failures"]}. Эталонные значения сами агенты не получают.','',
      f'Обучение: {data["lessons"]:,} новых шагов, {data["hard_lessons"]} адресных состояний сорока ошибок и их верных соответствий, {data["retention_lessons"]:,} прежних шагов для сохранения навыков. Сгенерированы 1200 новых учебных задач по семействам ошибок с другими числами и регистрами. В каждой паре совпадают расписание запусков/ревизий и таблица констант; правильность кода различается. Часть таблиц переставлена согласованно со ссылками.','',
      'Balanced и focused получают одинаковые выборки: 16 из 64 строк каждого обновления посвящены сорока ошибкам и их положительным соответствиям. Остальные строки включают новые варианты, старые навыки и текущие ошибки учеников. У обеих веток вес потерь HEX-тела увеличен до 2. У focused дополнительно вес адресных строк равен 2, а исправляемых байтов и границ удаления в HEX-ответе — 4. Служебные части запроса не усиливаются. Для исправлений используется весь правильный ответ, а не отдельный правильный параметр. Дополнительного парного прямого прохода нет.','',
      'На последнем доступном действии учитель даёт DONE для уже верной проверенной программы и UNSURE для неустранённой ошибки. Это 80 сопоставленных состояний; ещё 128 обучающих состояний поддерживают отказ при неполном условии. Новых вызовов большой LLM не было: учитель — авторские программы и ROM-проверка, включая память и явные требования.','',
      f'Выполнены {policy["blocks"]} × {policy["steps_per_block"]} обновлений каждой ветки, всего **{updates}**. Текущие ошибки обеих веток проверяются и объединяются между блоками. Q4 присутствует в каждом прямом проходе; перед SGD побитово сверены исходный пакет и все адаптируемые матрицы. Предварительная проверка выполнила 0 обновлений оптимизатора. Русские входные строки не обучались.','',
      'Новый контроль и экзамен зафиксированы до SGD и исключают точные тексты ранее использованных задач. Это новые формулировки/экземпляры знакомых семейств, а не неизвестные классы алгоритмов. Основной экзамен: 240 задач × верный/ошибочный старт = 480 эпизодов. Отдельно: 96 новых задач по семействам сорока ошибок (192 эпизода), 48 задач X²/X⁴ (192 эпизода) и 64 задачи с исходным компилятором. Старые сорок проверяются отдельно и не участвуют в выборе весов.','',
      '| Вариант | Решено /480 | Исправлено /240 | Завершено верных стартов /240 | Ложных DONE | UNSURE |','|---|---:|---:|---:|---:|---:|']
    all_results=[('Исходный адаптер',initial),*results.items()]
    for name,r in all_results:
        t=r['main']['raw'];lines.append(f'| {name} | {t["passed"]} | {t["repaired"]} | {t["correct_controls_completed"]} | {t["false_DONE"]} | {t["abstained"]} |')
        summary[name]={part:brief(r[part]['raw'])for part in ['main','neighbors','goals','from_scratch','reproduction']}
    lines+=['','Это raw-решения самой сети. Успех требует правильного кода, DONE и всех успешных публичных запусков. Ни отказы, ни правильный код без завершения успехом не считаются. Семантический порог не запрещает DONE в основном экзамене; полный диагностический прогон с этим непригодным ранее фильтром не повторялся.','',
      'Преждевременные DONE без всех успешных публичных запусков: '+', '.join(f'{name}: {r["main"]["raw"]["premature_DONE"]}'for name,r in all_results)+'. Они также провалы.','',
      '| Вариант | Новые варианты ошибок: решено /192 | Ложных DONE | X²/X⁴: решено /192 | Ложных DONE | С нуля /64 |','|---|---:|---:|---:|---:|---:|']
    for name,r in all_results:
        n=r['neighbors']['raw'];g=r['goals']['raw'];s=r['from_scratch']['raw']
        lines.append(f'| {name} | {n["passed"]} | {n["false_DONE"]} | {g["passed"]} | {g["false_DONE"]} | {s["passed"]} |')
    old=initial['main']['raw'];new=results[selected]['main']['raw'];og=initial['goals']['raw'];ng=results[selected]['goals']['raw']
    on=initial['neighbors']['raw'];nn=results[selected]['neighbors']['raw']
    lines+=['',f'У выбранной ветки на новых задачах: основной успех {old["passed"]} → {new["passed"]}, ложные DONE {old["false_DONE"]} → {new["false_DONE"]}; новые варианты разобранных ошибок {on["passed"]} → {nn["passed"]}, ложные DONE {on["false_DONE"]} → {nn["false_DONE"]}.']
    if ng['passed']<og['passed']or ng['false_DONE']>og['false_DONE']:
        lines+=['',f'Есть регрессия X²/X⁴: успех {og["passed"]} → {ng["passed"]}, ложные DONE {og["false_DONE"]} → {ng["false_DONE"]}. Этот профиль нельзя считать общим улучшением всех прежних навыков. Исходный адаптер сохранён; в прошивку новый профиль не установлен.']
    lines+=['','Старые сорок — учебное воспроизведение, не новый экзамен:','',
      '| Вариант | Правильно завершено /40 | Ложных DONE | UNSURE |','|---|---:|---:|---:|']
    for name,r in all_results:
        t=r['reproduction']['raw'];lines.append(f'| {name} | {t["passed"]} | {t["false_DONE"]} | {t["abstained"]} |')
    native_repro=root/'targeted-native-reproductions.json'
    if native_repro.exists():
        records=json.loads(native_repro.read_text());lines+=['','Два незавершённых старых эпизода отдельно воспроизведены нативным Q4:','']
        for r in records:
            if r['pass']:continue
            lines.append('- '+r['task']+' Код '+('верен, но сеть повторяет WRITE/RUN и не завершает задачу.'if r['program_correct']else'не исправлен: повторяются определения метки, затем ответ обрывается на лимите генерации.'))
        lines+=['','Контрольная константа 6 в этом нативном прогоне исправлена и завершена правильно. [Полные протоколы]('+str(native_repro)+').']
    tasks={t['id']:t for t in read(root/'fresh-neighbors.jsonl')};lines+=['','Новые варианты по причинам исходных ошибок (правильные завершения):','',
      '| Семейство | Исходный | balanced | focused |','|---|---:|---:|---:|']
    for category in analysis['categories']:
        ids={t['id']for t in tasks.values()if t['error_family']==category};cells=[]
        for name,r in all_results:
            rows=[x for x in r['neighbors']['raw']['details']if x['id']in ids];cells.append(f'{sum(x["pass"]for x in rows)}/{len(rows)}')
        lines.append('| '+LABELS[category]+' | '+' | '.join(cells)+' |')
    lines+=['','Контрольная динамика: 320 основных эпизодов, 128 новых вариантов ошибок, 128 X²/X⁴.','',
      '| Ветка | Блок | Основной: решено | Ложных DONE | Варианты: решено | Ложных DONE | X²/X⁴: решено | Ложных DONE |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for block in range(1,policy['blocks']+1):
        values={arm:json.loads((root/arm/f'training-{block}.json').read_text())for arm in ARMS}
        assert values[ARMS[0]]['same_draw_digest']==values[ARMS[1]]['same_draw_digest']
        assert values[ARMS[0]]['counts']==values[ARMS[1]]['counts']
        for arm,v in values.items():
            t,n,g=[v['summary'][k]for k in ['main','neighbors','goals']]
            lines.append(f'| {arm} | {block} | {t["passed"]} | {t["false_DONE"]} | {n["passed"]} | {n["false_DONE"]} | {g["passed"]} | {g["false_DONE"]} |')
    lines+=['',f'Выбрано до открытия экзамена: **{selected}, блок {choice["block"]}**. Исходный адаптер включён как блок 0. Критерий: ноль ложных DONE на всех трёх контрольных панелях и ≥80% основного успеха; затем взвешенный успех со штрафом 2 за ложный DONE (веса 0.65/0.25/0.10). Критерий выпуска пройден: **{pre["release_eligible"]}**. Экзамен не меняет веса, гиперпараметры или пороги.','',
      '| Ветка | AUC оценки правильности на новых посещённых состояниях |','|---|---:|']
    for arm,r in results.items():lines.append(f'| {arm} | {auc(r["main"]["raw"]["calibration"]):.4f} |')
    from ha_protocol import assemble
    from full_isa_vm import FullVM,check_task
    from tasks import save_jsonl
    task_lookup={t['id']:t for t in read(root/'fresh.jsonl')};remaining=[];vm=FullVM()
    for seed,r in zip(read(root/'fresh-seeds.jsonl'),results[selected]['main']['raw']['details']):
        if not(r['finished']and not r['program_correct']):continue
        t=task_lookup[r['id']];code=assemble(r['body'],seed['pool'],'asm');checked=check_task(vm,code,t)
        bad=next((i for i,x in enumerate(checked['details'])if not x['pass']),None)
        failure=None
        if bad is not None:
            actual=checked['details'][bad]['segments'][0]['actual'];expected=(t['public_tests']+t['hidden_tests'])[bad]['segments'][0]['expected']
            failure={'case':bad,'public':bad<len(t['public_tests']),'actual_X':actual['numeric']['X'],'expected_X':expected['numeric']['X']}
        remaining.append({'task_id':t['id'],'task':t['task'],'group':t['group'],'seed':seed,'initially_correct':r['initially_correct'],
          'body':r['body'],'wrong_code':code,'reference_code':t['reference_code'],'first_failure':failure,'history':r['history']})
    save_jsonl(root/'new-false-DONE.jsonl',remaining)
    lines+=['','Оставшиеся неверные DONE нового основного экзамена: '+str(len(remaining))+'. Полные запросы, программы и воспроизведение сохранены в [new-false-DONE.jsonl]('+str(root/'new-false-DONE.jsonl')+').']
    lines+=['','AUC — описательное ранжирование зависимых состояний, не гарантия правильности.','',
      'Регрессии на четырёх прежних пользовательских запросах (они уже использовались при обучении):','',
      '| Запрос | balanced raw | focused raw | Нативный выбранный raw |','|---|---|---|---|']
    for i,r in enumerate(demos[ARMS[0]]['raw']):
        lines.append('| '+r['task']+' | '+' | '.join('решено'if demos[arm]['raw'][i]['pass']else'не решено'for arm in [*ARMS,'native-selected'])+' |')
    lines.append('')
    for arm,d in demos.items():lines.append(f'- {arm}: уже верные программы {sum(r["pass"]for r in d["already_correct"])}/{len(d["already_correct"])}; неполные условия UNSURE {d["unknown_correct"]}/{len(d["unknown"])}.')
    lines+=['','Нативное исполнение и размер:','']
    for arm,r in native['models'].items():
        lines.append(f'- {arm}: точная повторная упаковка/загрузка Q4; CPU/B200 {r["cpu_matches"]}/{r["probes"]}, C++/B200 {r["native_matches"]}/{r["probes"]}; MKA {r["package_bytes"]:,} байт.')
        if arm!='compiler':lines.append(f'  Решения семантического порога совпали {r["threshold_decisions_matched"]}/{r["probes"]}; максимальное расхождение margin {max(x["margin_error"]for x in r["details"]):.6g}.')
    regress=native['long_input_regression'];mem=native['models'][selected]
    lines += [f'- Один буфер весов {native["shared_weight_buffer_bytes"]:,} байт; FP32 KV на 1024 токена {mem["cache_bytes"]:,} байт; рабочая память {mem["workspace_bytes"]:,} байт; дополнительные логиты 32 896 байт. Переключение компилятор → отладчик → компилятор проверено.',
      f'- Сохранён исследовательский предел ввода {regress["input_byte_limit"]} байт. Токенизация {regress["prefixes_checked"]} длинных запросов совпала с HF; проверено до {regress["max_utf8_bytes_checked"]} байт. Полный пик памяти и скорость физического PicoCalc не измерены.',
      '- Исходники прошивки не изменены, профиль в устройство не устанавливался. Родительский адаптер, исходное основание/компилятор, корпус и учебные исходники проверены по хешам. Собственные GPU-задания завершены.','',
      'Локальный runner: [ag_chat.py]('+str(HERE/'ag_chat.py')+'), режим raw по умолчанию. Он принимает русский запрос, угол, открытые входы и необязательный исходный HEX. Заявление модели DONE само по себе не является доверенным доказательством.']
    path=HERE/'FALSE_DONE_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    result={'completed':True,'selected_arm':selected,'selected_block':choice['block'],'optimizer_updates':updates,'release_eligible':pre['release_eligible'],
      'baseline':summary['Исходный адаптер'],'results':{k:v for k,v in summary.items()if k!='Исходный адаптер'},'native_verification_complete':native['complete'],'physical_device_measured':False}
    write(root/'summary.json',result);state_path=HERE/'work-state.json';state=json.loads(state_path.read_text())
    if not state.get('false_done_v1',{}).get('completed'):
        state['completed_training_runs']=state.get('completed_training_runs',68)+2
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',258758)+updates
    state.update(phase='false_done_v1_complete',all_own_jobs_complete=True,active_experiment=None,next_action='Review measured false-DONE results; no firmware deployment requested.')
    state['false_done_v1']={'completed':True,'report':str(path),'root':str(root),'summary':result};write(state_path,state)
    print(json.dumps({'completed':True,'report':str(path),'selected_arm':selected,'release_eligible':pre['release_eligible']}),flush=True)


if __name__=='__main__':main()
