"""Report raw, sealed outcomes; never relax the acceptance rule after seeing scores."""
import argparse
import json
from pathlib import Path
from ac_common import HERE,ARMS,read,write
from ha_protocol import assemble,constants


def command_names(code,catalog):
    words=[];at=0
    while at<len(code):
        row=catalog.get(code[at],{});word=row.get('name',f'{code[at]:02X}')
        if row.get('takes_address')and at+1<len(code):at+=1;word+=f' {code[at]:02X}'
        words.append(word);at+=1
    return '; '.join(words)


def brief(value):return {k:v for k,v in value.items()if k!='details'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    pre=json.loads((root/'preselected.json').read_text());native=json.loads((root/'native-verification.json').read_text())
    data=json.loads((root/'data-frozen.json').read_text());policy=json.loads((root/'policy.json').read_text())
    baseline=json.loads((root/'baseline.json').read_text());retention=json.loads((root/'compiler-retention.json').read_text())
    results={arm:json.loads((root/(arm+'-audit.json')).read_text())for arm in ARMS}
    updates=policy['warmup_steps']+2*policy['blocks']*policy['steps_per_block'];pilot_updates=200
    summary={'selected_arm':pre['selected_arm'],'release_eligible_validation':pre['release_eligible'],
      'highest_curriculum_level':pre['highest_curriculum_level'],'main_optimizer_updates':updates,
      'discarded_pilot_updates':pilot_updates,'all_new_updates':updates+pilot_updates,
      'native_verification_complete':native['complete'],'physical_picocalc_measured':False,'results':{}}
    lines=['# Отладка МК-61: замороженный компилятор и Q4 LoRA','',
      'Законченный исследовательский прогон. Сама модель выполняет программирование и выбор инструментов. В прошивку ничего не установлено.','',
      'Исходная Flourish-3M содержит 3 022 080 параметров. Первый код генерирует неизменённый исходный компилятор v3. Для последующих действий используется отдельный профиль с обученными Q/V LoRA ранга 4 и головкой из пяти действий. Обучалось 18 560 параметров: 17 920 в адаптерах и 640 в головке. Входной русский словарь сохранён.','',
      'На SD нужны два файла весов. При переключении профиля используется один и тот же буфер весов и один KV-кеш; два экземпляра модели в RAM не держатся. После слияния адаптеров каждый профиль остаётся обычной 3M Q4. Это не увеличение числа параметров исполняемой модели.','',
      'Действия: WRITE полного HEX, RUN с индексом публичного примера, TRACE, DONE, UNSURE. PATCH и DIAG исключены; осталась одна форма кода с прежними обратимыми FF-макросами. В выходном множестве 29 строк: 5 действий, 23 HEX-токена и разделитель. Входной праймер < кодируется отдельно; управляющий токен не подаётся в KV, вместо него вставляется однозначный заголовок WRITE или RUN.','',
      'Учитель использует настоящий ROM-эмулятор и эталоны только офлайн. В обратную связь ученику попадают фактические запуски, регистры и трасса без скрытых ожидаемых ответов. Контрпримеры попарно имеют одинаковую ревизию, историю WRITE/RUN/TRACE и бюджет. Есть неудачные прежние исправления. Одни и те же программа, входы и факты сопоставлены разным целям; пары симметричны в обе стороны.','',
      f'Корпус: {data["lessons"]:,} учебных шагов и {data["preferences"]:,} пар попыток; точные числа см. data-frozen.json. Представлены все 216 документированных кодов команд. Основной экзамен: 250 новых русских задач × правильный/ошибочный старт = 500 эпизодов, от 1 до 4 публичных входов. Отдельно проверяются 160 эпизодов пар с разными целями и 64 задачи с нуля. Это новые формулировки и значения, включая знакомые семейства, а не доказательство переноса на произвольные алгоритмы.','',
      'SFT: CE действия + средняя CE всех байтов тела, веса 1:1. Вторая ветка получает тот же SFT с теми же контрольными суммами выборок и дополнительно DPO полных выполненных траекторий (включая HEX-тела, beta=0.1, вес=0.1), с общей стартовой моделью в роли фиксированного сравнения. Претренировочная проверка доказала ненулевой градиент на аргументы при одинаковых действиях. В каждом прямом проходе Q/V уже сливаются и округляются в Q4.','',
      f'Основной прогон: стартовые {policy["warmup_steps"]} обновлений головки и две ветки по {policy["blocks"]} × {policy["steps_per_block"]}; всего {updates}. Дополнительно был отброшенный пилот из {pilot_updates} обновлений головки до исправления симметрии пар. Веса пилота не переиспользовались. Исходная база во время всего обучения побитово заморожена.','',
      'Переход от одиночных ошибок к составным разрешён, только если обе ветки на простом контрольном наборе исправляют ≥90%, завершают ≥95% правильных стартов и имеют 0 ложных DONE. Требование выпуска: 0 ложных DONE и ≥80% строгого успеха на контроле, сохранение исходного компилятора. Выбор лучшего блока зафиксирован до открытия финального экзамена.','',
      '| Вариант | Блок | Исправил и завершил | Сохранил и завершил правильное | Строго решено | Ложных DONE | Ранних DONE | UNSURE |',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    entries=[('Исходный v3','—',baseline['fresh'])]+[(arm,str(pre['choices'][arm]['block']),results[arm]['tools'])for arm in ARMS]
    for arm,block,t in entries:
        lines.append(f'| {arm} | {block} | {t["repaired"]}/{t["initially_wrong"]} | {t["correct_controls_completed"]}/{t["correct_controls"]} | {t["passed"]}/{t["total"]} | {t["false_DONE"]} | {t["premature_DONE"]} | {t["abstained"]} |')
    lines+=['','Финальные задачи по сложности:','','| Вариант | Простые: исправлено | Простые: ложных DONE | Составные: исправлено | Составные: ложных DONE |','|---|---:|---:|---:|---:|']
    for arm,block,t in entries:
        s=t['simple'];lines.append(f'| {arm} | {s["repaired"]}/{s["initially_wrong"]} | {s["false_DONE"]} | {t["repaired"]-s["repaired"]}/{t["initially_wrong"]-s["initially_wrong"]} | {t["false_DONE"]-s["false_DONE"]} |')
    if pre['highest_curriculum_level']==1:lines+=['','Обе ветки остались на первой ступени. На составных задачах в этом прогоне SGD не выполнялся, поскольку заданный порог простых отладок не достигнут. Их финальные результаты показывают перенос с первой ступени.']
    for arm,r in results.items():
        summary['results'][arm]={'selected_block':pre['choices'][arm]['block'],'tools':brief(r['tools']),
          'goal_twins':brief(r['goal_twins']),'from_scratch':brief(r['from_scratch']),
          'compiler_language':[r['compiler_language']['passed'],r['compiler_language']['total']],
          'release_eligible_fresh':r['tools']['false_DONE']==0 and r['tools']['passed']/r['tools']['total']>=.8}
    summary['baseline']=brief(baseline['fresh'])
    lines+=['','Контроль по блокам (не финальный экзамен):','','| Ветка | Блок | Исправлено простых | Правильных сохранено | Ложных DONE на простых | Строго решено всего |','|---|---:|---:|---:|---:|---:|']
    for block in range(1,policy['blocks']+1):
        left=json.loads((root/'sft'/f'training-{block}.json').read_text());right=json.loads((root/'outcome'/f'training-{block}.json').read_text())
        assert left['sample_plan_digest']==right['sample_plan_digest']and left['SFT_counts']==right['SFT_counts']
        for arm,r in [('sft',left),('outcome',right)]:
            t=r['summary']['tools'];s=t['simple']
            lines.append(f'| {arm} | {block} | {s["repaired"]}/{s["initially_wrong"]} | {s["correct_controls_completed"]}/{s["correct_controls"]} | {s["false_DONE"]} | {t["passed"]}/{t["total"]} |')
    lines+=['','Строгий успех требует одновременно правильной программы на публичных и скрытых проверках, явного DONE и выполнения всех публичных входов на последней версии. Ложный DONE — завершённая моделью, но неверная по смыслу программа; ранний DONE — неполное покрытие публичных входов. UNSURE и исчерпанный бюджет считаются нерешёнными. Структурный ограничитель DONE при оценке отключён.','',
      f'Выбран исследовательский профиль **{pre["selected_arm"]}**. Условие выпуска на контроле выполнено: **{pre["release_eligible"]}**. Максимальная достигнутая ступень: **{pre["highest_curriculum_level"]}**.','',
      '| Вариант | Пары разных целей | С нуля | Исходный компилятор: новые задачи |',
      '|---|---:|---:|---:|']
    for arm,r in results.items():lines.append(f'| {arm} | {r["goal_twins"]["passed"]}/{r["goal_twins"]["total"]} | {r["from_scratch"]["passed"]}/{r["from_scratch"]["total"]} | {r["compiler_language"]["passed"]}/{r["compiler_language"]["total"]} |')
    lines+=['',f'Компилятор: **{retention["isa"]["passed"]}/648** документированных команд/угловых режимов и **{retention["legacy"]["passed"]}/98** старых формул. Это точное сохранение отдельного исходного профиля; эти результаты не приписываются инструментальному профилю.','',
       'Нативная проверка на хосте:','']
    for arm,r in native['models'].items():lines.append(f'- {arm}: CPU/B200 {r["cpu_matches"]}/{r["probes"]}, C++/B200 {r["native_matches"]}/{r["probes"]}; точное переупаковывание Q4; файл MKA {r["package_bytes"]:,} байт.')
    tool=native['models'][pre['selected_arm']]
    lines+=[f'- Общий буфер весов {native["shared_weight_buffer_bytes"]:,} байт; KV FP32 на 1024 токена {tool["cache_bytes"]:,} байт; рабочая память ядра {tool["workspace_bytes"]:,} байт.',
       f'- Переключения компилятор → инструмент → компилятор проверены в одном буфере. Парсер: {native["parser"]["roundtrips_and_python_masks_matched"]} проверок, {native["parser"]["state_bytes"]} байт.',
       '- Полный пик RAM прошивки и скорость на физическом PicoCalc не измерялись. Два файла требуют места на SD; runtime, эмулятор и интерфейс требуют дополнительной RAM.','']
    demos=json.loads((root/'user-reproductions.json').read_text())
    lines+=['Проверки пользовательских примеров после выбора весов:','',
            '| Запрос/ошибка | SFT | Полные предпочтения | C++ выбранного |','|---|---:|---:|---:|']
    for i,row in enumerate(demos['sft']['reproductions']):lines.append('| '+row['task']+' | '+' | '.join('решено'if demos[k]['reproductions'][i]['pass']else'не решено'for k in ['sft','outcome','native-selected'])+' |')
    lines.append('| Неполные условия: верный UNSURE | '+' | '.join(f'{demos[k]["unknown_passed"]}/{len(demos[k]["unknown"])}'for k in ['sft','outcome','native-selected'])+' |')
    catalog={r['code']:r for r in json.loads((root/'catalog.json').read_text())};lookup={t['id']:t for t in read(root/'fresh.jsonl')+read(root/'fresh-goal-twins.jsonl')}
    failures=[r for r in results[pre['selected_arm']]['tools']['details']if r['finished']and not r['program_correct']]
    if failures:
        lines+=['','Примеры ложного DONE выбранного профиля (эталон приведён только для разбора после экзамена):','']
        failures.sort(key=lambda r:(r['level'],len(r['body']or[])))
        seen=set()
        for row in failures:
            if row['id']in seen:continue
            seen.add(row['id']);task=lookup[row['id']]
            try:code=assemble(row['body'],task.get('constants')or constants(task['task']),'asm')
            except ValueError:code=[]
            lines+=[f'- Запрос: «{task["task"]}» ({task["angle"]}). Модель объявила DONE с программой `{bytes(code).hex(" ").upper()}` — {command_names(code,catalog)}. Эталон: {command_names(task["reference_code"],catalog)}.']
            if len(seen)>=2:break
    lines+=['','Файлы: export/compiler, export/sft, export/outcome, export/selected-research. CLI: ac_chat.py --root PATH --angle DEG --inputs JSON QUESTION. Для отладки готовой программы: --initial-hex "..." (обычные машинные байты МК-61). Runtime не знает эталон ответа, поэтому verified_task_success всегда null; DONE остаётся заявлением модели.','',
       'Все собственные GPU-задания завершены. Хеши исходных весов, замороженного корпуса, учебного кода и приватного эмулятора проверены; подробности в postflight.json. Преобразование старого XML RUN в список аргументов исправлено только в отдельном контрольном адаптере ac_baseline.py; сохранённые учебные исходники не менялись.']
    report=HERE/'DEBUG_ADAPTER_RESULTS.md';report.write_text('\n'.join(lines)+'\n');write(root/'summary.json',summary)
    path=HERE/'work-state.json';state=json.loads(path.read_text())
    if not state.get('debug_adapter_v2',{}).get('completed'):
        state['completed_training_runs']=state.get('completed_training_runs',59)+4
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',239358)+updates+pilot_updates
    state.update(phase='debug_adapter_v2_complete',all_own_jobs_complete=True,active_experiment=None,next_action='Review debugging results; no automatic firmware deployment.')
    state['debug_adapter_v2']={'completed':True,'report':str(report),'selected_artifact':str(root/'export/selected-research/model.mka'),'summary':summary};write(path,state)
    print(json.dumps({'completed':True,'selected_arm':pre['selected_arm'],'release_eligible':pre['release_eligible'],'tools':{a:results[a]['tools']['passed']for a in ARMS},'report':str(report)}),flush=True)


if __name__=='__main__':main()
