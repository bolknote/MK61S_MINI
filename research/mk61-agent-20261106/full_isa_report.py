"""Report measured command coverage separately from programming ability."""
import argparse
import collections
import json
from pathlib import Path

from full_isa_common import read, write
from full_isa_vm import FullVM

LABELS=['baseline','full-best','protected-best','full-endpoint','protected-endpoint']


def count(value):
    return f'{value["passed"]}/{value["total"]}'


def compact(row):
    initial={r['id']:r['pass']for r in row['main']['details']}
    tool=row['tools'];tool_rows=tool['details']
    return {'documented':row['main']['documented_instructions'],'by_kind':row['main']['by_kind'],
      'by_group':row['main']['by_group'],'by_angle':row['main']['by_angle'],'by_opcode':row['main']['by_opcode'],
      'natural':{k:row['natural'][k]for k in ['passed','total','valid_calls']},
      'legacy':{k:row['legacy'][k]for k in ['passed','total','rate']},
      'tools':{**{k:tool[k]for k in ['passed','total']},
        'same_subset_without_tools':sum(initial[r['id']]for r in tool_rows),
        'recovered':sum(not initial[r['id']]and r['pass']for r in tool_rows),
        'tasks_with_second_turn':sum(len(r['history'])>1 for r in tool_rows),
        'trace_requests':sum(bool(h.get('trace'))for r in tool_rows for h in r['history'])},
      'observed_user_reproductions':{k:row['observed_user_reproductions'][k]for k in ['passed','total']},
      'language_nll':row['language']['nll']}


def paired(before,after):
    b={r['id']:r['pass']for r in before['details']};a={r['id']:r['pass']for r in after['details']}
    assert a.keys()==b.keys()
    return {'wins':sum(not b[k]and a[k]for k in b),'losses':sum(b[k]and not a[k]for k in b),
      'unchanged':sum(b[k]==a[k]for k in b),'paired_total':len(b)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root.resolve()
    reports={label:json.loads((root/'results'/(label+'.json')).read_text())for label in LABELS}
    training={arm:json.loads((root/arm/'training.json').read_text())for arm in ['full','protected']}
    assert all(v['completed']and v['steps']==8000 for v in training.values())
    assert training['full']['sample_plan_digest']==training['protected']['sample_plan_digest']
    assert training['full']['counts']==training['protected']['counts']
    prepared=json.loads((root/'prepared.json').read_text());policy=json.loads((root/'policy.json').read_text())
    teacher=json.loads((root/'teacher/manifest.json').read_text());selection=json.loads((root/'preselected.json').read_text())
    final=json.loads((root/'final-export.json').read_text());chosen=final['selected_label'];selected=reports[chosen]
    manifest=json.loads((root/'export/selected-budget/manifest.json').read_text())
    verification=json.loads((root/'local-verification.json').read_text());native=json.loads((root/'native-verification.json').read_text())
    context=json.loads((root/'context-verification.json').read_text());postflight=json.loads((root/'postflight.json').read_text())
    catalog=json.loads((root/'catalog.json').read_text());baseline=reports['baseline']
    doc=selected['main']['documented_instructions'];kinds=selected['main']['by_kind']
    milestones={'documented_instructions_95_percent':doc['rate']>=.95,
      'numeric_synthesis_80_percent':kinds['numeric_synthesis']['rate']>=.8,
      'programming_80_percent':kinds['programming']['rate']>=.8,
      'stateful_80_percent':kinds['interactive_game']['rate']>=.8}
    opcode_rows=selected['main']['by_opcode'];documented=[x for x in catalog if x['risk']=='documented']
    all_modes_mastered=sum(opcode_rows[x['hex']]['passed']==opcode_rows[x['hex']]['total']for x in documented)
    tasks={x['id']:x for x in read(root/'observed-user-reproductions.jsonl')};vm=FullVM();sine=[]
    for row in selected['observed_user_reproductions']['details']:
        if row['id']not in ['user-repro:sin:RAD:22','user-repro:sin:DEG:22','user-repro:sin:GRAD:22']:continue
        task=tasks[row['id']];case=task['public_tests'][0]['segments'][0]
        state=vm.execute(row['code'],case['inputs'],angle=task['angle'])[0]if row['code']else None
        sine.append({'id':row['id'],'angle':row['angle'],'pass':row['pass'],'reply':row['reply'],
          'actual_X':state['raw']['X']if state else None,'expected_X':case['expected']['raw']['X']})
    scores={label:compact(row)for label,row in reports.items()}
    summary={'selected_label':chosen,'selected_step':manifest['selected_step'],'selection_used_audit':False,
      'results':scores,'paired_main':{label:paired(baseline['main'],row['main'])for label,row in reports.items()},
      'reference_opcode_count':256,'documented_opcode_count':216,'documented_opcodes_passing_all_modes':all_modes_mastered,
      'reference_coverage_is_not_model_mastery':True,'milestones':milestones,'all_milestones_met':all(milestones.values()),
      'optimizer_updates_each':8000,'examples_each':training['full']['actual_examples'],
      'sample_plan_digest':training['full']['sample_plan_digest'],'teacher_verified':teacher['verified'],
      'selected_packed_sha256':manifest['packed_sha256'],'selected_packed_bytes':manifest['packed_bytes'],
      'parameters':manifest['parameters'],'cpu_b200_matches':[verification['cpu_b200_matches'],verification['compared']],
      'fp16_fp32_matches':[verification['fp16_fp32_matches'],verification['compared']],
      'native_matches':{k:[v['native_generations_match'],v['probes']]for k,v in native['models'].items()},
      'context':context['scores'],'sine22':sine,'physical_picocalc_measured':False,
      'free_language_programming_proven':False,'postflight':postflight}
    write(root/'comparison.json',summary)
    # Keep every documented instruction visible, including failures.
    opcode_lines=['# По каждой документированной команде МК-61','',
      'Три условия на команду: RAD, DEG и GRAD. Успех требует совпадения полного состояния, памяти и IP с настоящим ядром. Для большинства команд режим углов ничего не меняет. Прямые адреса не засчитываются как команды.',
      '', '| HEX | Команда | Исходная /3 | full-best /3 | protected-best /3 | Выбранная /3 | Точный HEX выбранной /3 |',
      '|---|---|---:|---:|---:|---:|---:|']
    for op in documented:
        key=op['hex'];vals=[reports[k]['main']['by_opcode'][key]['passed']for k in ['baseline','full-best','protected-best',chosen]]
        opcode_lines.append('| '+key+' | '+op['name'].replace('|','\\|')+' | '+' | '.join(map(str,vals))+f' | {opcode_rows[key]["exact"]} |')
    opcode_report=Path(__file__).with_name('FULL_ISA_OPCODE_RESULTS.md');opcode_report.write_text('\n'.join(opcode_lines)+'\n')
    lines=['# 3M HEX: полный набор команд МК-61','',
      f'Выбран **{chosen}**, шаг **{manifest["selected_step"]}** из 8000, по валидации до открытия новой проверки. '
      f'Документированные команды: **{count(doc)}** условий; **{all_modes_mastered}/216** команд прошли во всех трёх режимах углов.',
      '', '| Снимок | Документированные /648 | Научные составные /288 | Программирование /135 | Продолжения /10 | Новые формулировки /153 | Прежние /98 | Инструменты /100 |',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    for label in LABELS:
        row=reports[label];k=row['main']['by_kind']
        vals=[row['main']['documented_instructions']['passed'],k['numeric_synthesis']['passed'],k['programming']['passed'],
          k['interactive_game']['passed'],row['natural']['passed'],row['legacy']['passed'],row['tools']['passed']]
        lines.append('| '+label+' | '+' | '.join(map(str,vals))+' |')
    lines += ['', 'Исходная модель оценена с тем же новым полным HEX-протоколом. Её прежнее обучение требовало `<calc>`, поэтому нулевой результат на новом формате сам по себе не означает отсутствия арифметических знаний. До/после здесь сравниваются при одинаковом интерфейсе.',
      'Показатели команд проверяют перевод словесного поручения в конкретную инструкцию и исполнение. Они не доказывают умение написать произвольную программу из этих команд. Отдельно проверены составные вычисления, переходы, циклы, запись памяти, подпрограммы и продолжения после С/П.',
      '', '## Синус 22','', '| Режим | Ответ модели | X эмулятора | Эталон X | Прошёл |', '|---|---|---|---|---|']
    for row in sine:
        lines.append(f'| {row["angle"]} | `{row["reply"]}` | {row["actual_X"]} | {row["expected_X"]} | '+('да'if row['pass']else'нет')+' |')
    lines += ['', 'Запрос про синус 22 уже был известен до этого раунда, поэтому это воспроизведение пользовательского случая, а не независимая новая задача. Результаты отличаются между RAD, DEG и GRAD; режим задаёт harness.',
      '', '## Покрытие и качество по группам','', '| Группа | Исходная | Выбранная |', '|---|---:|---:|']
    for group,value in selected['main']['by_group'].items():
        lines.append('| '+group+' | '+count(baseline['main']['by_group'][group])+' | '+count(value)+' |')
    lines += ['', 'Все 256 байтов доступны выходу; это 216 документированных вариантов команд, 32 недокументированных и 8 опасных/ошибочных кодов в каталоге. Регистровые варианты входят в эти числа: это не 216 независимых математических функций. Служебные и недокументированные коды показаны отдельно от документированных. Их эталон может завершаться ожидаемой ошибкой или лимитом.',
      f'Полная таблица каждой документированной команды: [{opcode_report.name}]({opcode_report}).',
      '', '| Режим углов, все виды основных задач | Исходная | Выбранная |', '|---|---:|---:|']
    for angle,value in selected['main']['by_angle'].items():lines.append('| '+angle+' | '+count(baseline['main']['by_angle'][angle])+' | '+count(value)+' |')
    lines += ['', '## Как обучали','',
      f'Архитектура и русский входной словарь сохранены: **{manifest["parameters"]:,} параметров**, 8224 входных строки (8192 исходных и 32 неиспользуемых строки прежнего опыта), 37 выходных токенов. Выход — полная программа `<write>HEX</write><run/>`, а также `<trace/>` и `<done/>`. Обязательной формулы из семи операций и дописываемого за модель начала ответа нет.',
      f'Канонический набор: 7768 условий — 4608 на все коды и режимы, 2200 на научные вычисления, 900 на программирование и 60 на реальные остановы/продолжения. Добавлены 160 проверенных четырёхкомандных фрагментов старых игр и **{teacher["verified"]}** перефразировок большого учителя. Повторение старого курса: **{prepared["legacy_rows"]}** условий. Реальные ошибки исходного студента: **{prepared["actual_initial_errors"]}**, синтетические ошибки для исправлений: **{prepared["synthetic_errors"]}**.',
      'Первый вариант генерации учителя был отброшен до обновления весов: без справочника учитель путал X и R0 и ошибался в кодах. В исправленном варианте генератор видел условие без эталонного HEX, а отдельный вызов восстанавливал программу с полным общим справочником команд. Его код исполнялся на всех тестах исходного условия. Это два вызова одной большой модели, а не независимая человеческая экспертиза. Проверочные условия учителю не передавались.',
      f'Два варианта получили по **8000 обновлений**, по **{training["full"]["actual_examples"]:,} строк** с идентичным планом выборки. В full обновлялись все входные эмбеддинги, в protected — только 37 строк, также используемых компактным выходом. Остальные {verification["protected_input_embeddings"]["protected-endpoint"]["unchanged_rows"]} строк protected побитно совпадают с исходными. Прочие слои обучались в обоих вариантах.',
      f'Q4 с первого обновления; LR {policy["lr"]}, для эмбеддингов вдвое меньше; проверка каждые 500 обновлений. Контексты 512/1024/2048 с долями 85/10/5%. Из 128 строк каждого обновления шесть сохраняли русский язык и учили вспомогательной последовательности команд через полный русский выход. На исполнении оставлены только 37 токенов HEX/инструментов.',
      'Корпус книг и описаний игр использован в языковом повторении. Шестьсот целых игр в этом раунде не стали шестьюстами независимо проверенными программами. Исторические фрагменты и короткие игры с продолжениями — ограниченная часть практики.',
      '', 'Промежуточная валидация (новая итоговая проверка для выбора не использовалась):','',
      '| Вариант | Шаг | Команды | Научные | Программы | Продолжения | Прежние |', '|---|---:|---:|---:|---:|---:|---:|']
    for arm,report in training.items():
        for row in report['history']:
            s=row['summary'];k=s['kinds']
            lines.append(f'| {arm} | {row["step"]} | '+count(s['documented'])+' | '+count(k['numeric_synthesis'])+' | '+count(k['programming'])+' | '+count(k['interactive_game'])+' | '+count(s['legacy'])+' |')
    lines += ['', '## Ограничения новой проверки','',
      'Основная проверка содержит 1201 условие: 768 инструкционных (256 × 3), 288 научных составных, 135 программных и 10 с настоящими последовательными запусками. Для команд сравниваются X/Y/Z/T/X1, все R0–RE, статус и IP. Для составных задач — функциональный результат и сохранение всей памяти. Числа проверяются с точностью настоящего микрокодового ядра МК-61, а не только стандартной математической библиотеки.',
      '153 новые русские формулировки — контролируемые задания 17 семейств, по три угловых режима и три варианта композиции. Повторяющиеся семейства не являются 153 независимыми человеческими задачами. Качество на произвольных игровых алгоритмах этим не установлено.',
      'Инструменты проверены на заранее выбранных 100 заданиях, не более трёх ходов. В обратную связь попадают только открытые тесты; скрытые служат итоговой оценке. Поиска программы, детерминированного решения или вызова большого учителя во время исполнения нет.',
      f'На этой же сотне выбранная модель без обратной связи решила {scores[chosen]["tools"]["same_subset_without_tools"]}, с обратной связью — {scores[chosen]["tools"]["passed"]}. Исправлено ранее не решённых: {scores[chosen]["tools"]["recovered"]}; запросов TRACE: {scores[chosen]["tools"]["trace_requests"]}. Уже правильный первый ответ не засчитывается как доказательство исправления ошибки.',
      'Свободные русские рассуждения эта сборка не выводит: компактный выход содержит HEX и инструменты. Вспомогательные русские планы использовались только при обучении; сами по себе они не доказывают наличие устойчивого режима рассуждений. Наблюдаемый агентный навык здесь — составить программу, увидеть ошибку эмулятора и попробовать исправить её.',
      '', '## Контекст и пакет для PicoCalc','', '| Контекст | Решено коротких /12 | Сохранено с заметками | Длина входа, максимум токенов |', '|---|---:|---:|---:|']
    for length,value in context['scores'].items():lines.append(f'| {length} | {value["solved_short"]} | {value["retained_long"]} | {value["max_prompt_tokens"]} |')
    selected_native=native['models'][chosen];small=selected_native['context1024']
    lines += ['', 'Контекстная проверка выполнена на CPU после выбора весов: одинаковые задачи с посторонними заметками и без них, удержание считается среди решённых коротких. Это проверка удержания условия, а не полноценной долгой агентной памяти.',
      f'Q4-пакет выбранной модели: **{manifest["packed_bytes"]:,} байт**. Все пять пакетов повторно экспортированы и загружены, ошибка загрузки относительно точных Q4-весов — ноль. Совпадение токенов CPU/B200: **{verification["cpu_b200_matches"]}/{verification["compared"]}**; хранение KV в FP16 против FP32: **{verification["fp16_fp32_matches"]}/{verification["compared"]}**.',
      'Для всех пяти снимков собраны MKA с контекстом 2048 и 1024. Генерации проверены на частной копии нативного C++ runtime; исходники продукта не менялись. Физический PicoCalc не измерялся.',
      f'Нативный runtime хранит KV в FP32: при 2048 токенах кеш занимает {selected_native["native_cache_bytes"]:,} байт и превышает 8 МиБ. В пакете `model-context1024.mka` те же веса, KV {small["native_cache_bytes"]:,} байт, workspace {small["workspace_bytes"]:,} байт. Общую память и скорость на плате ещё нужно измерить. FP16 KV проверен на хосте, но пока не внедрён в этот нативный runtime.',
      f'Если MKA целиком загружен в RAM, сумма файла модели, KV и указанного workspace при контексте 1024 — {small["package_plus_cache_and_workspace_bytes"]:,} байт ({small["package_plus_cache_and_workspace_bytes"]/1024**2:.2f} МиБ). Прочие данные runtime и прошивки в эту сумму не входят.',
      '', '## Итог и артефакты','',
      'Ориентиры курса: ≥95% инструкционных условий, ≥80% научных составных, ≥80% программных и ≥80% продолжений. Выполнены все: **'+('да'if all(milestones.values())else'нет')+'**. Это ориентиры ограниченного набора; успешное произвольное программирование ещё не доказано.',
      f'- [Выбранный Q4]({root}/export/selected-budget/model.mkqb)',
      f'- [MKA с контекстом 1024]({root}/export/selected-budget/model-context1024.mka)',
      f'- [Полные результаты]({root}/comparison.json)',
      f'- [Проверка native и хеши]({root}/native-verification.json)',
      f'- [Фиксация выбора до итоговой проверки]({root}/preselected.json)',
      '', f'SHA256 выбранного Q4: `{manifest["packed_sha256"]}`.',
      'Исходные веса, замороженные наборы, языковые потоки и частная копия ядра не изменились. Наши контроллеры завершены, контейнеры освобождены; состояние GPU сохранено в postflight.json.']
    report_path=Path(__file__).with_name('FULL_ISA_RESULTS.md');report_path.write_text('\n'.join(lines)+'\n')
    state_path=Path(__file__).with_name('work-state.json');state=json.loads(state_path.read_text())
    previous=state.get('full_isa_v1',{});counted=previous.get('completed',False)
    state['phase']='full_isa_v1_complete';state['all_own_jobs_complete']=True;state['free_language_coding_target_met']=False
    state['full_isa_v1']={**previous,'completed':True,'selected_label':chosen,'selected_step':manifest['selected_step'],
      'optimizer_updates_each':8000,'teacher_verified':teacher['verified'],'documented_scores':doc,
      'documented_opcodes_passing_all_modes':all_modes_mastered,'milestones':milestones,'report':str(report_path),
      'artifact':str(root/'export/selected-budget/model.mkqb'),'selected_packed_sha256':manifest['packed_sha256']}
    if not counted:
        state['completed_training_runs']=state.get('completed_training_runs',0)+2
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',0)+16000
    write(state_path,state)
    print(json.dumps({'selected':chosen,'scores':scores[chosen],'sine22':sine,'milestones':milestones,'report':str(report_path)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
