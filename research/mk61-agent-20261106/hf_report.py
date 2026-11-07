"""Report learned completion separately from the execution bookkeeping gate."""
import argparse
import json
from pathlib import Path

from hf_common import HERE,write


def without_details(panel):return {k:v for k,v in panel.items()if k!='details'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    labels=['asm-baseline','safe-best','active-best'];reports={k:json.loads((root/'results'/(k+'.json')).read_text())for k in labels}
    final=json.loads((root/'final-export.json').read_text());chosen=final['selected_label'];selection=json.loads((root/'preselected.json').read_text())
    training={k:json.loads((root/k/'training.json').read_text())for k in ['safe','active']}
    assert all(v['completed']and v['steps']==2000 for v in training.values())
    assert training['safe']['sample_plan_digest']==training['active']['sample_plan_digest']
    model=json.loads((root/'export/selected-budget/manifest.json').read_text());frozen=json.loads((root/'data-frozen.json').read_text())
    native=json.loads((root/'native-verification.json').read_text());local=json.loads((root/'local-verification.json').read_text())
    gate=json.loads((root/'native-frontend/debug-gate-verification.json').read_text());post=json.loads((root/'postflight.json').read_text())
    result={}
    for name,r in reports.items():
        result[name]={'fresh':[r['language']['passed'],r['language']['total']],'groups':r['language']['by_group'],
          'documented':r['isa']['documented'],'stop':r['isa']['by_opcode']['50'],'legacy':[r['legacy']['passed'],r['legacy']['total']],
          'observed_retention':[r['observed_retention']['passed'],r['observed_retention']['total']],
          'observed_ablation':[r['observed_ablation']['passed'],r['observed_ablation']['total']],
          'user':[r['observed_user_reproductions']['passed'],r['observed_user_reproductions']['total']],
          **{k:without_details(r[k])for k in ['tools','tools_gated','from_scratch']}}
    selected=result[chosen];tool=selected['tools'];nt=native['models'][chosen]
    fresh_stop=selected['groups']['stop_command']
    target=(selected['stop']['rate']==1 and fresh_stop['rate']==1 and selected['documented']['rate']==1
            and tool['false_accepts']==0 and tool['repaired']/max(1,tool['initially_wrong'])>=.8
            and tool['correct_controls_completed']/max(1,tool['correct_controls'])>=.9
            and tool['unfinished_correct']/max(1,tool['total'])<=.05)
    summary={'selected_label':chosen,'selected_step':model['selected_step'],'parameters':model['parameters'],'packed_sha256':model['packed_sha256'],
      'results':result,'fresh_used_for_selection':False,'retention_guard_passed':selection['choices'][selection['primary_selected_arm']]['best_key'][0],
      'observed_target_met':target,'same_training_draws':True,'updates_each':2000,'native_gate':gate,'postflight':post,
      'cpu_b200_matches':[local['cpu_b200_matches'],local['compared']],'native_matches':sum(v['native_generations_match']for v in native['models'].values()),
      'physical_picocalc_measured':False,'gate_guarantees_semantics':False}
    smoke_path=root/'boundary-smoke.json'
    if smoke_path.exists():
        smoke=json.loads(smoke_path.read_text());summary['native_boundary_smoke']={k:{a:b for a,b in smoke[k].items()if a!='details'}for k in ['asm-baseline',chosen]}
    demo_path=root/'native-repair-demo.json'
    if demo_path.exists():
        demo=json.loads(demo_path.read_text());summary['native_repair_demo']={k:v for k,v in demo.items()if k!='details'}
    write(root/'comparison.json',summary)
    lines=['# 3M Q4: С/П, отладка и завершение задачи','',
      f'Выбран **{chosen}**, шаг **{model["selected_step"]}**, по валидации до итогового нового экзамена. Начальные веса — `harness-debug-v2/{frozen["initial_selected_label"]}`, шаг {frozen["initial_selected_step"]}. Контекст 1024; обычные HEX-команды и прежние макросы констант/меток.',
      'Начальный запрос генерации кода побайтно сохранён. Формат входов, накопленных фактов и инструментов совпадает с v2. Этот проход добавляет размеченные состояния из собственных траекторий предыдущего студента и усиливает повторение формул.',
      '', '| Снимок | Новые задачи | С/П | Документированные | Прежние формулы /98 | Повтор прежнего курса /360 |',
      '|---|---:|---:|---:|---:|---:|']
    for name,s in result.items():
        lines.append(f'| {name} | {s["fresh"][0]}/{s["fresh"][1]} | {s["stop"]["passed"]}/{s["stop"]["total"]} | {s["documented"]["passed"]}/{s["documented"]["total"]} | {s["legacy"][0]} | {s["observed_retention"][0]} |')
    lines+=['', '| Тип новой задачи | Начальный снимок | Выбранный снимок |','|---|---:|---:|']
    for group,v in selected['groups'].items():
        b=result['asm-baseline']['groups'][group];lines.append(f'| {group} | {b["passed"]}/{b["total"]} | {v["passed"]}/{v["total"]} |')
    lines+=['', '## Навык модели без блокировки DONE',
      'Все варианты используют одинаковые новые условия, входные состояния, ошибочные старты и предел шести ходов. В этой таблице harness принимает DONE без блокировки: она показывает решения самой сети.',
      '', '| Снимок | Верная программа и DONE | Исправлено неверных стартов | DONE при неверном коде | Верный код без DONE | PATCH |',
      '|---|---:|---:|---:|---:|---:|']
    for name,s in result.items():
        t=s['tools'];lines.append(f'| {name} | {t["passed"]}/{t["total"]} | {t["repaired"]}/{t["initially_wrong"]} | {t["false_accepts"]} | {t["unfinished_correct"]} | {t["patch_requests"]} |')
    lines+=['', '## Тот же экзамен с контролем выполненных запусков',
      'После WRITE/PATCH сводка прошлых запусков сбрасывается. DONE разрешён, когда все открытые случаи выполнены для текущей версии и эмулятор остановился без ошибки. Этот контроль не знает эталонного X, не читает скрытые случаи и не гарантирует правильности вычисления. Сеть должна сама сопоставить фактический результат с условием.',
      '', '| Снимок | Верная программа и DONE | Неверных завершений | Отклонено преждевременных DONE | Неверных попыток DONE до блокировки |',
      '|---|---:|---:|---:|---:|']
    for name,s in result.items():
        t=s['tools_gated'];lines.append(f'| {name} | {t["passed"]}/{t["total"]} | {t["false_accepts"]} | {t["premature_done_rejected"]} | {t["wrong_done_attempts"]} |')
    lines+=['', 'Статус stopped не считается доказательством верности. Эталоны используются при подготовке проверенных уроков и в итоговом проверяющем, но не в доступной модели обратной связи. Готовность произвольного программиста этим синтетическим экзаменом не установлена.',
      '', '## Корпус и обучение',
      f'Повторяются {frozen["counts"]["train"]} обучающих условий; валидационных {frozen["counts"]["validation"]}, новых итоговых {frozen["counts"]["fresh"]}. Зафиксированный предыдущий студент прошёл {frozen["episodes"]} обучающих эпизодов. Из его состояний размечено {frozen["dagger_lessons"]} дополнительных уроков, среди них {frozen["actual_error_episodes"]} неверных DONE. Итоговые и валидационные задачи при сборе этих траекторий не использовались.',
      'Каждый сохранённый запрос воспроизведён побайтно. Внешний учитель на ядре МК-61 проверил текущую программу: неверной соответствует WRITE проверенной программы, верной с непроверенными входами — RUN, полностью проверенной верной — DONE. Эталон не включается во вход модели. Сохраняются и прежние уроки TRACE/PATCH.',
      'Две B200: по 2000 обновлений и 256000 строк, одинаковые семантические выборки, LR safe — 5e-6, active — 1e-5. 40 из 128 строк — новые состояния, 16 — прежние инструменты, 32 — прежние формулы, 12 — составные выражения, 10 — ISA, 2 — С/П. Неиспользуемые выходом строки русского словаря защищены; новых вызовов большой модели-учителя в этом раунде не было.',
      'Задачи синтетические, с эталонами на настоящем ядре МК-61. Прежний экзамен /360 теперь наблюдаемый: часть его реальных ошибок вошла в обучение. Родственные семейства могли встречаться исходной сети раньше; варианты с разными входами не являются независимыми человеческими задачами.',
      '', f'Валидационное ограничение сохранения навыков пройдено: **{"да"if summary["retention_guard_passed"]else"нет"}**. Итоговая наблюдаемая цель (все команды и новые формулировки С/П, ≥80% исправлений, ноль неверных DONE без блокировки, ≥90% завершения верных контрольных программ и ≤5% верного кода без DONE) достигнута: **{"да"if target else"нет"}**.',
      '', '## Нативная проверка',
      f'Q4 всех трёх экспортов повторно загружен и экспортирован без изменения полезных данных. CPU/B200 совпали в {local["cpu_b200_matches"]}/{local["compared"]} пробах, FP16/FP32 KV — в {local["fp16_fp32_matches"]}/{local["compared"]}. C++ совпал с B200 в {summary["native_matches"]}/{local["compared"]} пробах. Нативный контроль запусков совпал с Python на {gate["python_cpp_state_transitions_matched"]} переходах; его состояние — {gate["state_bytes"]} байт.',
      f'Пакет MKA — {nt["package_bytes"]} байт. MKA + FP32 KV + рабочая область модели — {nt["package_plus_kv_workspace_bytes"]} байт ({nt["package_plus_kv_workspace_bytes"]/1048576:.2f} MiB), без остальной памяти прошивки. Физический PicoCalc пока не измерялся.',
      '', f'- [Q4]({root}/export/selected-budget/model.mkqb)',f'- [MKA, контекст 1024]({root}/export/selected-budget/model.mka)',
      f'- [Контракт]({root}/export/selected-budget/protocol.json)',f'- [Все результаты]({root}/comparison.json)',
      f'- [Нативный контроль DONE]({root}/export/selected-budget/runtime/hf_gate.hpp)',
      '', f'SHA256 Q4: `{model["packed_sha256"]}`. GPU-контейнеры и контроллеры этого эксперимента завершены; исходные веса, замороженные данные и ядро не изменились.']
    if 'native_boundary_smoke'in summary:
        lines+=['', '## Короткие пользовательские запросы в C++-цикле','',
          '| Снимок | Верный код с первого ответа | Верный код и DONE |','|---|---:|---:|']
        for label,s in summary['native_boundary_smoke'].items():lines.append(f'| {label} | {s["first_program_correct"]}/{s["total"]} | {s["finished_correct"]}/{s["total"]} |')
        lines += ['Набор наблюдаемый, используется после выбора весов; эталон не передаётся модели.',f'[Журнал]({smoke_path})']
    if demo_path.exists():
        lines += ['', '## Нативные демонстрации исправления',
          'Это наблюдаемые диагностические примеры после выбора снимка. Они не участвовали в выборе весов.',
          '', '| Задача с неверным стартом | Исправлено и завершено |', '|---|---:|']
        for row in demo['details']:lines.append(f'| {row["question"]} | {"да"if row["pass"]else"нет"} |')
        lines += ['Лишний квадрат X исправлен. Косинус вместо синуса 22 и единица вместо нуля остались неверными, но модель выдала DONE. Эти примеры подтверждают, что один DONE не является доказательством правильности.',f'[Полный журнал]({demo_path})']
    lines += ['', 'CLI `hf_chat.py` отдельно возвращает `model_declared_done` и `verified_task_success=null`: без независимых критериев модельный DONE не объявляется подтверждённым успехом задачи.']
    path=HERE/'HARNESS_DEBUG_V3_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    state_path=HERE/'work-state.json';state=json.loads(state_path.read_text());counted=state.get('harness_debug_v3',{}).get('completed',False)
    state.update(phase='harness_debug_v3_complete',all_own_jobs_complete=True,free_language_coding_target_met=False)
    state['harness_debug_v3']={'completed':True,'selected_label':chosen,'selected_step':model['selected_step'],
      'results':result,'report':str(path),'artifact':str(root/'export/selected-budget/model.mkqb'),'observed_target_met':target,
      'updates_each':2000,'gate_guarantees_semantics':False}
    if not counted:state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=4000
    write(state_path,state)
    print(json.dumps({'selected':chosen,'fresh':selected['fresh'],'stop':selected['stop'],'tools':selected['tools'],'report':str(path)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
