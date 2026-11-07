"""Report the format ablation, oracle-free repairs and preservation limits."""
import argparse
import collections
import json
from pathlib import Path

from ha_common import read,write

LABELS=[arm+'-'+role for arm in ['direct','asm']for role in ['baseline','best','endpoint']]


def pair(x):return [x['passed'],x['total']]


def compact(x):
    t=x['tools']
    return {'language':pair(x['language']),'groups':x['language']['by_group'],'documented':x['isa']['documented'],
      'isa_groups':x['isa']['by_group'],'isa_kinds':x['isa']['by_kind'],'legacy':pair(x['legacy']),
      'observed_previous_language':pair(x['observed_previous_language']),'user_reproductions':pair(x['observed_user_reproductions']),
      'tools':{k:v for k,v in t.items()if k!='details'},'intermediate_programs_correct':sum(r['program_correct']for r in t['details']),
      'language_nll':x['public_language']['nll']}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    reports={label:json.loads((root/'results'/(label+'.json')).read_text())for label in LABELS}
    training={arm:json.loads((root/arm/'training.json').read_text())for arm in ['direct','asm']}
    assert all(x['completed']and x['steps']==4000 for x in training.values())
    assert training['direct']['sample_plan_digest']==training['asm']['sample_plan_digest']
    assert training['direct']['counts']==training['asm']['counts']
    selection=json.loads((root/'preselected.json').read_text());final=json.loads((root/'final-export.json').read_text())
    chosen=final['selected_label'];manifest=json.loads((root/'export/selected-budget/manifest.json').read_text())
    frozen=json.loads((root/'data-frozen.json').read_text());prepared=json.loads((root/'prepared.json').read_text())
    local=json.loads((root/'local-verification.json').read_text());native=json.loads((root/'native-verification.json').read_text())
    agent=json.loads((root/'agent-from-scratch.json').read_text());post=json.loads((root/'postflight.json').read_text())
    scores={k:compact(v)for k,v in reports.items()};goals={}
    for arm in ['direct','asm']:
        s=scores[arm+'-best'];groups=s['groups'];n=sum(groups[k]['passed']for k in ['literal_copy','literal_function']);d=sum(groups[k]['total']for k in ['literal_copy','literal_function'])
        goals[arm]={'literal_at_least_90_percent':n/d>=.9,'composition_at_least_80_percent':groups['composition']['rate']>=.8,
          'documented_full_exam_100_percent':s['documented']['rate']==1.,
          'validation_retention_guard_passed':bool(selection['choices'][arm]['best_key'][0]),'literal_score':[n,d]}
    before={r['id']:r for r in reports['direct-best']['language']['details']};after={r['id']:r for r in reports['asm-best']['language']['details']}
    wins=sum(not before[k]['pass']and after[k]['pass']for k in before);losses=sum(before[k]['pass']and not after[k]['pass']for k in before)
    both=[k for k in before if before[k]['pass']and after[k]['pass']]
    savings={'paired_tasks':len(before),'asm_only_correct':wins,'direct_only_correct':losses,'both_correct':len(both),
      'mean_generated_tokens_direct_on_both_correct':sum(before[k]['generated_tokens']for k in both)/len(both)if both else None,
      'mean_generated_tokens_asm_on_both_correct':sum(after[k]['generated_tokens']for k in both)/len(both)if both else None,
      'same_task_weighted_bootstrap_not_independent_human_benchmark':True}
    summary={'selected_label':chosen,'selected_step':manifest['selected_step'],'fresh_used_for_selection':False,'results':scores,
      'goals':goals,'paired_format_comparison':savings,'parameters':manifest['parameters'],'packed_bytes':manifest['packed_bytes'],
      'selected_packed_sha256':manifest['packed_sha256'],'updates_each':4000,'same_semantic_sample_plan':True,
      'sample_plan_digest':training['direct']['sample_plan_digest'],'data_counts':frozen['counts'],'tool_episodes':prepared['tool_episodes'],
      'tool_lessons':prepared['tool_lessons'],'actual_pretrained_errors':prepared['actual_pretrained_errors'],
      'cpu_b200_matches':[local['cpu_b200_matches'],local['compared']],'fp16_fp32_matches':[local['fp16_fp32_matches'],local['compared']],
      'native_frontend':native['frontend'],'agent_from_scratch':{k:{a:b for a,b in v.items()if a!='details'}for k,v in agent.items()},
      'physical_picocalc_measured':False,'postflight':post}
    write(root/'comparison.json',summary)
    lines=['# 3M Q4: полный HEX и HEX с константами/метками','',
      f'По заранее заданной валидации выбран **{chosen}**, шаг **{manifest["selected_step"]}**. '
      'В начале у обеих моделей одни и те же веса `full-isa-natural-v1/protected-best`, шаг 2500. Итоговый новый экзамен не участвовал в выборе.',
      '', '| Снимок | Новые задачи | Документированные /648 | Прежние формулы /98 | Повтор прежних русских /606 | Исправлено испорченных | Завершено инструментальных |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for label in LABELS:
        s=scores[label];t=s['tools']
        lines.append(f'| {label} | {s["language"][0]}/{s["language"][1]} | {s["documented"]["passed"]} | {s["legacy"][0]} | {s["observed_previous_language"][0]} | {t["repaired"]}/{t["initially_wrong"]} | {t["passed"]}/{t["total"]} |')
    lines += ['', 'Исходные веса проверены отдельно с каждым новым входным протоколом. Это измеряет стоимость перехода формата; прежние 355/606 при старом протоколе нельзя напрямую приравнивать к новым базовым результатам.',
      '', '## Что изменил формат','', '| Тип новых задач | Лучший полный HEX | Лучший ассемблерный HEX |', '|---|---:|---:|']
    for group,value in scores['direct-best']['groups'].items():
        other=scores['asm-best']['groups'][group]
        lines.append(f'| {group} | {value["passed"]}/{value["total"]} | {other["passed"]}/{other["total"]} |')
    lines += ['', f'На одинаковых новых задачах только ассемблерный вариант решил {wins}, только прямой HEX — {losses}. Оба решили {len(both)}. '
      f'Среди решённых обоими средняя длина генерации: {savings["mean_generated_tokens_direct_on_both_correct"]:.1f} токена у direct и {savings["mean_generated_tokens_asm_on_both_correct"]:.1f} у asm.',
      'Обе модели выбирают всю программу. У asm только четыре детерминированные директивы: FF00 выдаёт обычный байт FF, FF01kk разворачивает указанную константу в команды ввода, FF02ll задаёт метку, FF03ll выдаёт её адрес в кодировке МК-61. Все остальные байты остаются командами МК-61. Доступны все 256 кодовых значений; промежуточный язык не ограничен семью арифметическими операциями.',
      'Таблица констант извлекается из условия лексически и передаётся обеим моделям. Ассемблер не выбирает операции, не восстанавливает формулу из русского текста и не решает задачу за модель. Русский словарь и архитектура 3M сохранены; у компактного выхода теперь 40 существующих токенов.',
      '', '## Исправления без подсказки правильного ответа','', '| Вариант | Восстановлено неверных | Ошибочно завершено неверных | TRACE | PATCH | RUN другого случая |', '|---|---:|---:|---:|---:|---:|']
    for arm in ['direct','asm']:
        s=scores[arm+'-best'];t=s['tools']
        lines.append(f'| {arm} | {t["repaired"]}/{t["initially_wrong"]} | {t["false_accepts"]} | {t["trace_requests"]} | {t["patch_requests"]} | {t["run_requests"]} |')
    lines += ['', 'Каждый запуск получает только заданные открытые входы и возвращает фактические X/Y, изменения памяти, IP и статус. Трасса выдаётся по запросу. В наблюдениях нет ожидаемого X и нет oracle-меток PASS/FAIL. Скрытые случаи недоступны инструменту и используются только итоговым проверяющим.',
      'Начальные ошибочные программы обеих моделей после развёртки побайтно одинаковы. Успех требует правильного результата на всех открытых и скрытых случаях и явного DONE в пределах четырёх ходов. Правильная промежуточная программа без DONE отдельно сохранена в данных, но не считается завершённой задачей.',
      'Программа, таблица констант, выбранный тест и журнал запусков хранятся во внешнем состоянии harness. Модель видит исходное условие, текущую программу и последнее наблюдение. PATCH заменяет суффикс программы с указанной позиции; каждый запрос ограничен 1024 токенами, условие не обрезается.',
      '', 'Дополнительная проверка на CPU — начать с пустого кода и выполнить весь цикл, максимум пять ходов (после выбора весов, без влияния на выбор):','',
      '| Вариант | Верная итоговая программа | Верная программа и DONE |', '|---|---:|---:|']
    for arm,v in agent.items():lines.append(f'| {arm} | {v["program_correct"]}/{v["total"]} | {v["passed"]}/{v["total"]} |')
    lines += ['', '## Корпус, обучение и ограничения','',
      f'Новый корпус: {frozen["counts"]["train"]} обучающих условий, {frozen["counts"]["validation"]} для валидации и {frozen["counts"]["fresh"]} для нового экзамена. Вводимые новые числа разделены по хешу значения. Формулировки различаются между наборами; это родственные синтетические семейства, а не независимый человеческий экзамен.',
      'Задачи включают точный ввод дробей и отрицательных чисел, различение X и R0–RE, составные выражения, ограничение диапазона, ветвления и подпрограммы. Эти короткие законченные алгоритмы написаны для эксперимента; 600 целых игр в этом раунде не оценивались. Книги и старые игровые данные остаются в языковом повторении и прежнем корпусе.',
      f'Инструментальных эпизодов {prepared["tool_episodes"]}, отдельных уроков {prepared["tool_lessons"]}. Реальных ошибок исходного студента — {prepared["actual_pretrained_errors"]}; остальные старты — детерминированные мутации и правильные контрольные программы. Правильные исправления и тестовые эталоны вычислялись при подготовке корпуса; при исполнении модели доступен только обычный эмулятор.',
      'Оба варианта обучены по 4000 обновлений, по 512000 строк. Одинаковые начальные веса, порядок семантических примеров, контекст 1024, LR 2e-5 и Q4 с первого обновления. В основной части 28 из 128 строк посвящены инструментам. Длинные примеры допускаются только если помещаются у обоих форматов. Все 256 кодов реально присутствовали в выборках.',
      'Снимки выбирались по валидации. Для обоих вариантов до обучения зафиксированы одинаковые нижние границы прежних формул, вычислений и программ; допуск — три процентных пункта от лучшего исходного результата при новых протоколах. Полное сохранение документированных команд обязательно для прохождения валидационного ограничения.',
      '', '| Вариант | ≥90% запросов с константами | ≥80% составных | Все документированные на полном экзамене | Прошёл ограничение регрессий на валидации |', '|---|---|---|---|---|']
    for arm,g in goals.items():lines.append('| '+arm+' | '+' | '.join('да'if g[k]else'нет'for k in ['literal_at_least_90_percent','composition_at_least_80_percent','documented_full_exam_100_percent','validation_retention_guard_passed'])+' |')
    lines += ['', 'Наличие правильного HEX для всех отдельных команд не доказывает умение программировать произвольные задачи. Свободные русские рассуждения не выводятся; проверяемые навыки — построение программы, запрос фактической трассы, редактирование и повторный запуск.',
      '', '## Нативный пакет и память','',
      f'Размер выбранной модели: {manifest["parameters"]:,} параметров, Q4 {manifest["packed_bytes"]:,} байт. Точные пакеты всех шести экспортов повторно загружены и экспортированы без изменения полезных данных. Уникальных наборов весов: {local["unique_weight_payloads"]}; оба протокола проверялись даже при одинаковых начальных весах.',
      f'Совпадение токенов CPU/B200 — {local["cpu_b200_matches"]}/{local["compared"]}; хранение KV в FP16 против FP32 — {local["fp16_fp32_matches"]}/{local["compared"]}. MKA собраны с контекстом 1024, полезные данные весов совпадают с проверенным Q4.',
      f'C++-фронтенд совпал с Python на {native["frontend"]["pool_extractions_matched"]} таблицах констант и {native["frontend"]["program_expansions_matched"]} развёртках. Состояние фронтенда — {native["frontend"]["native_state_bytes"]} байт, рабочая область ассемблера — {native["frontend"]["native_assembler_workspace_bytes"]} байт; динамических выделений нет.',
      'Нативные проверки используют частную копию C++ runtime. Физический PicoCalc пока не измерялся; KV в этом runtime остаётся FP32. Размеры не включают всю прочую память прошивки.',
      '', '## Артефакты','',
      f'- [Выбранный Q4]({root}/export/selected-budget/model.mkqb)',
      f'- [MKA, контекст 1024]({root}/export/selected-budget/model.mka)',
      f'- [Контракт harness]({root}/export/selected-budget/protocol.json)',
      f'- [C++-фронтенд]({root}/export/selected-budget/runtime/ha_native.hpp)',
      f'- [Все оценки]({root}/comparison.json)',
      f'- [Выбор до нового экзамена]({root}/preselected.json)',
      '', f'SHA256 выбранного Q4: `{manifest["packed_sha256"]}`.',
      'Исходные веса, замороженные наборы, языковые потоки и частное ядро не изменились. Наши GPU-контейнеры и контроллеры завершены; postflight.json содержит состояние GPU после завершения.']
    path=Path(__file__).with_name('HARNESS_ABLATION_RESULTS.md');path.write_text('\n'.join(lines)+'\n')
    catalog=json.loads((root/'catalog.json').read_text());opcode_lines=['# По каждой документированной команде','', '| HEX | Команда | direct-best /3 | asm-best /3 |', '|---|---|---:|---:|']
    for op in catalog:
        if op['risk']!='documented':continue
        key=op['hex'];opcode_lines.append('| '+key+' | '+op['name'].replace('|','\\|')+f' | {reports["direct-best"]["isa"]["by_opcode"][key]["passed"]} | {reports["asm-best"]["isa"]["by_opcode"][key]["passed"]} |')
    path.with_name('HARNESS_ABLATION_OPCODES.md').write_text('\n'.join(opcode_lines)+'\n')
    state_path=Path(__file__).with_name('work-state.json');state=json.loads(state_path.read_text());previous=state.get('harness_ablation_v1',{});counted=previous.get('completed',False)
    state['phase']='harness_ablation_v1_complete';state['all_own_jobs_complete']=True;state['free_language_coding_target_met']=False
    state['harness_ablation_v1']={**previous,'completed':True,'selected_label':chosen,'selected_step':manifest['selected_step'],
      'scores':{k:scores[k]for k in ['direct-best','asm-best']},'goals':goals,'report':str(path),
      'artifact':str(root/'export/selected-budget/model.mkqb'),'selected_packed_sha256':manifest['packed_sha256']}
    if not counted:
        state['completed_training_runs']=state.get('completed_training_runs',0)+2
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',0)+8000
    write(state_path,state)
    print(json.dumps({'selected':chosen,'goals':goals,'comparison':{k:scores[k]['language']for k in ['direct-best','asm-best']},
      'tools':{k:scores[k]['tools']for k in ['direct-best','asm-best']},'report':str(path)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
