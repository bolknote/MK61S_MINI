"""Report paired semantic-debug training without hiding rejection/coverage tradeoffs."""
import argparse
import json
from pathlib import Path
from ae_common import HERE,ARMS,write,read


def brief(panel):return {k:v for k,v in panel.items()if k not in ['details','calibration']}


def auc(rows):
    values=sorted((r['margin'],r['truth'])for r in rows if r.get('margin')is not None);positive=sum(y for x,y in values);negative=len(values)-positive
    if not positive or not negative:return None
    rank_sum=0.;at=0
    while at<len(values):
        end=at+1
        while end<len(values)and values[end][0]==values[at][0]:end+=1
        rank_sum+=(at+1+end)/2*sum(y for x,y in values[at:end]);at=end
    return (rank_sum-positive*(positive+1)/2)/(positive*negative)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    pre=json.loads((root/'preselected.json').read_text());data=json.loads((root/'data-frozen.json').read_text());policy=json.loads((root/'policy.json').read_text())
    native=json.loads((root/'native-verification.json').read_text());demos=json.loads((root/'user-reproductions.json').read_text())
    baseline=json.loads((root/'initial-fresh-audit.json').read_text());results={arm:json.loads((root/(arm+'-fresh-audit.json')).read_text())for arm in ARMS}
    updates=policy['warmup_steps']+len(ARMS)*policy['blocks']*policy['steps_per_block'];summary={}
    lines=['# 3M Q4: составные отладки и отдельная оценка соответствия цели','',
       'Завершён парный прогон на двух B200. В прошивку ничего не установлено. После обучения проведены локальная проверка точного экспорта Q4, исполнения C++ и воспроизведения пользовательских ошибок.','',
       'Начало обеих веток — один и тот же прежний SFT-профиль отладчика, загруженный из реального Q4. Исходный компилятор v3 сохранён отдельным неизменённым профилем. Русские входные embedding-строки защищены. Выходы WRITE/RUN/TRACE/DONE/UNSURE и единственное представление HEX+обратимые FF-макросы сохранены.','',
       '- lora16: Q/V и MLP gate/up/down, rank16/alpha32; 318 336 обучаемых значений вместе с головками.',
       '- full: существующий transformer целиком, кроме входных embedding; 1 970 304 обучаемых значения вместе с головками.',
       '- После слияния и упаковки каждый исполняемый профиль содержит **3 022 080 параметров Q4**. Две строки семантической головки помещены в ранее свободные служебные строки; они не поступают на вход и не являются действиями протокола.','',
       f'Корпус: {data["task_counts"]["train"]} учебных задач и {data["lessons"]:,} размеченных шагов. 800 простых задач (включая все 216 документированных кодов), 600 композиций следующей ступени и 600 сложных/алгоритмических задач. Сложность обучается по фиксированному расписанию с первого блока, без ожидания идеального DONE. Пары имеют одинаковые ревизии, предупреждения и историю запусков, но разные программы либо разные цели при одинаковом коде. В части эпизодов переставлена явная таблица констант; все ссылки согласованно перекодированы.','',
       'Учитель этого прогона — программно составленные эталонные программы, проверенные полным ROM-исполнением и явными условиями задания. Новый вызов большой LLM в этом прогоне не использовался. Для собственных ошибок ученика эталонное исправление определяется соответствующей проверенной задачей; найденные самим учеником верные альтернативы проверяются тем же способом и добавляются в общий учебный пул.','',
       'Программа считается правильной по публичным и скрытым проверкам значений/памяти и дополнительным контрактам. В заданиях на подпрограмму требуется фактическое выполнение ПП и В/О. Примитивы с явно названными командами сохраняют эту команду и заданную раскладку. До SGD уточнено правило: DONE учителя допускается только при успешных публичных запусках. Предыдущий черновик корпуса сохранён отдельно; до исправления было 0 обновлений оптимизатора.','',
       'Целевая функция: CE действия + средняя CE всех HEX-аргументов + CE семантической правильности (вес неправильного класса 4) + дополнительное подавление вероятности DONE на неправильном текущем коде. Ошибка последнего вызова и правильность текущей программы размечаются отдельно. Нетипичный, но правильный код получает положительную семантическую метку даже после предупреждения. Неполные условия учат UNSURE, в том числе до написания программы.','',
       f'Общий старт: {policy["warmup_steps"]} обновлений только новой головки (256 значений); поведение старого компилятора/контроллера на этом этапе не обучалось. Затем {policy["blocks"]} × {policy["steps_per_block"]} обновлений каждой ветки: всего **{updates}**. Обе ветки используют одинаковые SFT-выборки; контрольные суммы и счётчики сверены после каждого блока. Данные текущих учеников объединяются между блоками. Q4 слитых матриц присутствует в каждом прямом проходе.','',
       'Экзамен зафиксирован до SGD: 240 новых задач × правильный/ошибочный старт = **480 эпизодов**, 1–4 публичных входа и дополнительные скрытые проверки. Дополнительно: пары разных целей, переставленные таблицы констант и 64 задачи с нуля. Это новые экземпляры частично знакомых семейств. Экзамен не используется для выбора весов или порога.','',
       '| Вариант | Режим | Решено /480 | Исправлено /240 | Правильных стартов завершено /240 | Ложных DONE | UNSURE |',
       '|---|---|---:|---:|---:|---:|---:|']
    t=baseline['main']['raw'];lines.append(f'| Прежний SFT | raw | {t["passed"]} | {t["repaired"]} | {t["correct_controls_completed"]} | {t["false_DONE"]} | {t["abstained"]} |')
    for arm,r in results.items():
        summary[arm]={}
        for mode,t in r['main'].items():
            lines.append(f'| {arm} | {mode} | {t["passed"]} | {t["repaired"]} | {t["correct_controls_completed"]} | {t["false_DONE"]} | {t["abstained"]} |')
            summary[arm][mode]=brief(t)
    lines+=['','Разбор основного raw-экзамена по сложности:','',
       '| Вариант | Простые /192 | Составные /192 | Сложные /96 |','|---|---:|---:|---:|']
    for name,r in [('Прежний SFT',baseline),*results.items()]:
        rows=r['main']['raw']['details'];counts=[sum(x['pass']for x in rows if x['level']==level)for level in [1,2,3]]
        lines.append('| '+name+' | '+' | '.join(map(str,counts))+' |')
    lines+=['','Raw показывает решения самого контроллера без внешнего запрета DONE. Calibrated дополнительно проверяет успешные запуски всех публичных случаев и порог новой семантической головки. При отказе модель получает сообщение и может исправлять дальше или выбрать UNSURE. Отказы и незавершённые правильные программы не считаются решёнными. Ни один режим не получает эталонные значения в обратной связи.','',
       'Семантический порог выбирается по контролю: выше максимального балла неверного состояния, между ним и ближайшим верным выше него. Это нулевое число ложных подтверждений на контроле по построению, а не гарантия на новых задачах. AUC ниже — описательное ранжирование посещённых состояний, которые не являются независимыми примерами.','',
       '| Ветка | Выбранный блок | Порог | AUC семантической головки на новых состояниях |','|---|---:|---:|---:|']
    for arm,r in results.items():lines.append(f'| {arm} | {pre["choices"][arm]["block"]} | {r["threshold"]:.6f} | {auc(r["main"]["raw"]["calibration"]):.4f} |')
    lines+=['','Дополнительные панели:','','| Ветка | Режим | Разные цели | Переставленные таблицы | С нуля |','|---|---|---:|---:|---:|']
    for arm,r in results.items():
        for mode in ['raw','calibrated']:
            parts=[r[p][mode]for p in ['twins','binding','from_scratch']]
            lines.append(f'| {arm} | {mode} | '+' | '.join(f'{p["passed"]}/{p["total"]}'for p in parts)+' |')
    lines+=['','Контрольная динамика:','','| Ветка | Блок | Решено /320 | Ложных DONE | Исправлено |','|---|---:|---:|---:|---:|']
    for block in range(1,policy['blocks']+1):
        left=json.loads((root/'lora16'/f'training-{block}.json').read_text());right=json.loads((root/'full'/f'training-{block}.json').read_text())
        assert left['same_draw_digest']==right['same_draw_digest']and left['counts']==right['counts']
        for arm,r in [('lora16',left),('full',right)]:
            t=r['summary']['main'];lines.append(f'| {arm} | {block} | {t["passed"]} | {t["false_DONE"]} | {t["repaired"]}/{t["initially_wrong"]} |')
    lines+=['',f'Исследовательский профиль выбран до экзамена: **{pre["selected_arm"]}**, блок **{pre["choices"][pre["selected_arm"]]["block"]}**. Критерий выпуска по основному raw-контролю (0 ложных DONE и ≥80% строгого успеха): **{pre["release_eligible"]}**.','',
       'Нативное исполнение:','']
    for arm,r in native['models'].items():
        lines.append(f'- {arm}: точная повторная упаковка/загрузка Q4; CPU/B200 {r["cpu_matches"]}/{r["probes"]}, C++/B200 {r["native_matches"]}/{r["probes"]}; MKA {r["package_bytes"]:,} байт.')
        if arm!='compiler':lines.append(f'  Семантические пороговые решения совпали {r["threshold_decisions_matched"]}/{r["probes"]}; максимальное расхождение margin {max(x["margin_error"]for x in r["details"]):.6g}.')
    first=native['models'][ARMS[0]]
    lines+=[f'- Один буфер весов {native["shared_weight_buffer_bytes"]:,} байт и один FP32 KV-кеш {first["cache_bytes"]:,} байт на 1024 токена. Рабочая память ядра {first["workspace_bytes"]:,} байт; временный массив логитов новой проверки {first["auxiliary_logits_buffer_bytes"]:,} байт.',
       '- Переключение компилятор → отладчик → компилятор проверено в одном буфере. Два профиля требуют двух файлов на SD; полный пик памяти интерфейса/эмулятора и скорость физического PicoCalc не измерены.',
       '- Исходный компилятор v3 побитово сохранён. Его прежний результат 648/648 документированных команд и 69/98 формул относится к этому отдельному профилю. Он не приписывается дообученным профилям отладчика.','',
       'Пользовательские примеры после выбора весов:','','| Запрос | lora16 raw | lora16 calibrated | full raw | full calibrated |','|---|---|---|---|---|']
    for i,row in enumerate(demos['lora16']['raw']):
        values=[demos[arm][mode][i]['pass']for arm in ARMS for mode in ['raw','calibrated']]
        lines.append('| '+row['task']+' | '+' | '.join('решено'if x else'не решено'for x in values)+' |')
    lines+=['',*['- Неполные условия, '+arm+': UNSURE '+str(demos[arm]['unknown_correct'])+'/'+str(len(demos[arm]['unknown']))+'.'for arm in [*ARMS,'native-selected']],
       '', 'Практическая оценка: адаптер дал заметный прирост именно на составных задачах (44 → 121 из 192), но исправил лишь половину ошибочных стартов в целом. Полное дообучение в данном бюджете уступило адаптеру; это результат этого расписания и двух разных скоростей обучения, а не доказательство превосходства LoRA вообще.',
       '', 'Строгий семантический фильтр в нынешнем виде непригоден для рабочего завершения: у адаптера 0 ложных DONE достигаются при всего 8 успешных завершениях из 480. Даже верный синус 22 он не пропускает. Порог и веса после просмотра экзамена не менялись.',
       '', 'Отдельные ошибки показывают, что нужен следующий адресный учебный набор. На «Выдай в X число 0» адаптер пишет правильную программу, затем многократно повторяет её и выбирает UNSURE. На «Вычисли квадрат текущего X» оставляет две команды квадрата, то есть X⁴, и заявляет DONE, хотя при X=2.5 эмулятор показывает 39.0625. На (X+1)*(X+1) исходный компилятор выдаёт ошибочный код с результатом −1, а отладчик его принимает. Синус 22 в DEG исправляет на FF 01 03 1C 50, запускает и получает 0.3746066; это воспроизведено нативным Q4.',
       '', 'Дальнейшая гипотеза обучения: собирать фактические ошибки связки компилятор+отладчик на отдельном новом учебном наборе; добавлять парные случаи X²/X⁴ и другие близкие цели с различающими входами; учить завершению уже правильного кода без повторной записи и исправлению после отказа головки. Отдельно оценивать полезную долю подтверждений при фиксированном риске, вместо одного порога выше любого ошибочного примера. Эти изменения ещё не обучены и их эффект не измерен. Текущий экзамен сохраняется как просмотренный; следующий контроль должен быть новым.',
       '', 'Для ручного воспроизведения подготовлен локальный runner [ae_chat.py]('+str(HERE/'ae_chat.py')+'). Он принимает русский запрос, угол, открытые входы и необязательный ошибочный HEX; поддерживает нативный исполнитель и явные режимы --mode raw / --mode calibrated. Итог model_declared_done является заявлением модели; verified_task_success остаётся null, поскольку runner не получает доверенного эталона.',
       '', 'Все собственные GPU-задания закончены. Проверены замороженный корпус, учебные исходники, исходные веса компилятора/отладчика и приватный эмулятор. Новая головка остаётся обучаемой оценкой; она не доказывает правильность программы для произвольного русского условия.']
    path=HERE/'SEMANTIC_DEBUG_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    result={'completed':True,'selected_arm':pre['selected_arm'],'release_eligible':pre['release_eligible'],'optimizer_updates':updates,
       'baseline':brief(baseline['main']['raw']),'results':summary,'native_verification_complete':native['complete'],'physical_device_measured':False}
    write(root/'summary.json',result);state_path=HERE/'work-state.json';state=json.loads(state_path.read_text())
    if not state.get('semantic_debug_v2',{}).get('completed'):
        state['completed_training_runs']=state.get('completed_training_runs',63)+3
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',244558)+updates
    state.update(phase='semantic_debug_v2_complete',all_own_jobs_complete=True,active_experiment=None,next_action='Review semantic-debug results; no automatic firmware deployment.')
    state['semantic_debug_v2']={'completed':True,'report':str(path),'root':str(root),'summary':result};write(state_path,state)
    print(json.dumps({'completed':True,'report':str(path),'selected_arm':pre['selected_arm'],'release_eligible':pre['release_eligible']}),flush=True)


if __name__=='__main__':main()
