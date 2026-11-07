import argparse
import json
from pathlib import Path
from hr_common import write


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    labels=['asm-baseline','slow-best','fast-best'];reports={k:json.loads((root/'results'/(k+'.json')).read_text())for k in labels}
    selection=json.loads((root/'preselected.json').read_text());final=json.loads((root/'final-export.json').read_text());chosen=final['selected_label']
    model=json.loads((root/'export/selected-budget/manifest.json').read_text());training={k:json.loads((root/k/'training.json').read_text())for k in ['slow','fast']}
    assert all(x['completed']and x['steps']==1200 for x in training.values());assert training['slow']['sample_plan_digest']==training['fast']['sample_plan_digest']
    local=json.loads((root/'local-verification.json').read_text());native=json.loads((root/'native-verification.json').read_text());post=json.loads((root/'postflight.json').read_text())
    scratch=json.loads((root/'agent-from-scratch.json').read_text());native_chosen=native['models'][chosen]
    smoke=json.loads((root/'boundary-smoke.json').read_text())if(root/'boundary-smoke.json').exists()else None
    results={}
    for name,r in reports.items():
        results[name]={'fresh':[r['language']['passed'],r['language']['total']],'groups':r['language']['by_group'],'documented':r['isa']['documented'],
          'legacy':[r['legacy']['passed'],r['legacy']['total']],'observed_ablation':[r['observed_ablation']['passed'],r['observed_ablation']['total']],
          'observed_previous_language':[r['observed_previous_language']['passed'],r['observed_previous_language']['total']],
          'user':[r['observed_user_reproductions']['passed'],r['observed_user_reproductions']['total']],
          'tools':{k:v for k,v in r['tools'].items()if k!='details'}}
    command_errors=[{k:r.get(k)for k in ['id','opcode','angle','reply','codec_error']}
                    for r in reports[chosen]['isa']['details']if r.get('catalog_risk')=='documented'and not r['pass']]
    summary={'selected_label':chosen,'selected_step':model['selected_step'],'fresh_used_for_selection':False,'format':'asm','results':results,
      'retention_guard_passed':selection['choices'][selection['primary_selected_arm']]['best_key'][0],
      'packed_sha256':model['packed_sha256'],'parameters':model['parameters'],'updates_each':1200,
      'cpu_b200_matches':[local['cpu_b200_matches'],local['compared']],'fp16_fp32_matches':[local['fp16_fp32_matches'],local['compared']],
      'documented_command_errors':command_errors,'all_documented_passed_on_final':not command_errors,
      'from_scratch':{k:{a:b for a,b in v.items()if a!='details'}for k,v in scratch.items()},
      'same_semantic_draws':True,'sample_plan_digest':training['slow']['sample_plan_digest'],'postflight':post,'physical_picocalc_measured':False}
    if smoke:
        summary['native_boundary_smoke']={label:{k:v for k,v in smoke[label].items()if k!='details'}for label in ['asm-baseline',chosen]}
    write(root/'comparison.json',summary)
    lines=['# Исправление граничных чисел и восстановление формул','',
      f'Выбран **{chosen}**, шаг **{model["selected_step"]}**. Начальные веса — `harness-ablation-v1/asm-best`, шаг 2500. Протокол констант и ассемблера не менялся.',
      '', '| Снимок | Новые граничные и глубокие задачи | Документированные /648 | Прежние формулы /98 | Повтор первого эксперимента /599 | Исправлено испорченных |',
      '|---|---:|---:|---:|---:|---:|']
    for name,s in results.items():lines.append(f'| {name} | {s["fresh"][0]}/{s["fresh"][1]} | {s["documented"]["passed"]} | {s["legacy"][0]} | {s["observed_ablation"][0]} | {s["tools"]["repaired"]}/{s["tools"]["initially_wrong"]} |')
    lines += ['', 'В первом сравнении ассемблерный вариант решил 571/599 новых задач, но обычные запросы с 0/1 вскрыли пробел корпуса. После этого отдельный курс добавил 0, 1, -1, отрицательный ноль, дроби, различение X и памяти и вложенные выражения на 4–8 операций. Старое сравнение сохранено отдельно; его 599 задач теперь являются наблюдаемой повторной проверкой.',
      'Новый курс: 2680 обучающих условий, 240 валидационных и 360 итоговых. Семейства новых глубоких выражений разделены по хешу; исходный снимок мог встречать родственные семейства в предыдущих курсах. Оба варианта получили одинаковый порядок примеров, по 1200 обновлений и 153600 строк. LR fast — 1e-5, slow — 2.5e-6; Q4 с первого обновления. Модели остаются 3M с русским входным словарём и 40 выходными токенами.',
      '', '| Тип новой проверки | До | Выбранная модель |', '|---|---:|---:|']
    for group,v in results[chosen]['groups'].items():
        b=results['asm-baseline']['groups'][group];lines.append(f'| {group} | {b["passed"]}/{b["total"]} | {v["passed"]}/{v["total"]} |')
    lines += ['', 'Валидационное ограничение требует не менее 64/98 прежних формул, полного сохранения документированных команд и прежних порогов вычислений/программ. Прошло: **'+('да'if summary['retention_guard_passed']else'нет')+'**. Новый итоговый набор не использовался для выбора снимка.',
      'Обратная связь инструментов осталась без эталонного X и без PASS/FAIL oracle. Скрытые случаи используются только итоговым проверяющим. Для инструментального успеха требуется верная программа и явный DONE; ложные завершения отдельно сохранены в results/*.json.',
      f'На полном итоговом экзамене документированных команд осталось ошибок: {len(command_errors)}. Прохождение ограничения на меньшей валидационной панели не означает отсутствия регрессий на полном наборе. Их конкретные коды и ответы сохранены в comparison.json.',
      '', '| Инструментальный цикл | До | Выбранная модель |', '|---|---:|---:|',
      f'| Правильная программа и DONE | {results["asm-baseline"]["tools"]["passed"]}/{results["asm-baseline"]["tools"]["total"]} | {results[chosen]["tools"]["passed"]}/{results[chosen]["tools"]["total"]} |',
      f'| Исправлено неверных стартов | {results["asm-baseline"]["tools"]["repaired"]}/{results["asm-baseline"]["tools"]["initially_wrong"]} | {results[chosen]["tools"]["repaired"]}/{results[chosen]["tools"]["initially_wrong"]} |',
      f'| DONE при неверной программе | {results["asm-baseline"]["tools"]["false_accepts"]} | {results[chosen]["tools"]["false_accepts"]} |',
      f'| Запросы TRACE / PATCH / RUN | {results["asm-baseline"]["tools"]["trace_requests"]} / {results["asm-baseline"]["tools"]["patch_requests"]} / {results["asm-baseline"]["tools"]["run_requests"]} | {results[chosen]["tools"]["trace_requests"]} / {results[chosen]["tools"]["patch_requests"]} / {results[chosen]["tools"]["run_requests"]} |',
      'Самостоятельная отладка остаётся слабым местом; обучение протоколу PATCH не гарантирует его применения на итоговых задачах. Готовность к произвольным русским заданиям этим экспериментом не подтверждена.',
      f'Дополнительный запуск с пустой программой на CPU, без влияния на выбор: slow — правильный код {scratch["slow"]["program_correct"]}/{scratch["slow"]["total"]}, правильный код с DONE {scratch["slow"]["passed"]}/{scratch["slow"]["total"]}; fast — {scratch["fast"]["program_correct"]}/{scratch["fast"]["total"]} и {scratch["fast"]["passed"]}/{scratch["fast"]["total"]} соответственно. Это десять диагностических примеров, а не полный экзамен агента.',
      '', f'Все три Q4-экспорта повторно загружены и экспортированы без изменения полезных данных. CPU/B200 совпали в {local["cpu_b200_matches"]}/{local["compared"]} пробах, FP16/FP32 хранение KV — в {local["fp16_fp32_matches"]}/{local["compared"]}. MKA проверены в частной копии C++ runtime с контекстом 1024. Физический PicoCalc пока не измерялся.',
      f'Выбранный MKQB — {model["packed_bytes"]} байт; MKA — {native_chosen["package_bytes"]}. MKA + FP32 KV + рабочая область модели — {native_chosen["package_plus_kv_workspace_bytes"]} байт, около {native_chosen["package_plus_kv_workspace_bytes"]/1048576:.2f} MiB. Остальная память прошивки в эту сумму не входит. Внешнее состояние программы не увеличивает внимание модели сверх 1024 токенов.',
      '', f'- [Выбранный Q4]({root}/export/selected-budget/model.mkqb)',f'- [MKA, контекст 1024]({root}/export/selected-budget/model.mka)',
      f'- [Контракт формата]({root}/export/selected-budget/protocol.json)',f'- [C++-фронтенд]({root}/export/selected-budget/runtime/ha_native.hpp)',
      f'- [Все результаты]({root}/comparison.json)',f'- [Исходное сравнение форматов]({Path(__file__).with_name("HARNESS_ABLATION_RESULTS.md")})',
      '', f'SHA256 Q4: `{model["packed_sha256"]}`. Наши GPU-контейнеры и контроллеры завершены; исходные веса и замороженные наборы не изменились.']
    if smoke:
        lines += ['', '## Короткие пользовательские запросы в нативном цикле',
                  '', '| Снимок | Верный код с первого ответа | Верный код и DONE за пять ходов |', '|---|---:|---:|']
        for label in ['asm-baseline',chosen]:
            s=smoke[label];lines.append(f'| {label} | {s["first_program_correct"]}/{s["total"]} | {s["finished_correct"]}/{s["total"]} |')
        lines += ['Это наблюдаемая диагностика после выбора снимка: по два разных открытых входных состояния и одному дополнительному состоянию только у проверяющего. Эталонные ответы не передаются модели. Проверяются X и сохранность регистров. На выбор весов эти пробы не влияют.',
                  'У выбранного снимка исправлены 0, 1, -1, дроби, sin(0), sin(22), квадрат и корень текущего X. Выражение `(X+1)*(X+1)` остаётся неверным. Квадрат и корень X вычисляются верно, но цикл не завершается DONE за пять ходов.',
                  f'[Полный журнал нативных проб]({root}/boundary-smoke.json)',
                  '', 'Воспроизводимый запуск на компьютере с нативным исполнением модели:', '', '```sh',
                  str(Path(__file__).resolve().parents[2]/'.build/squeal-chat-20261105/venv/bin/python')+' '+str(Path(__file__).resolve().with_name('ha_chat.py'))+' \'Подсчитай синус 22.\' --angle DEG --native --model '+str(root/'export/selected-budget'),
                  '```', 'В градусах результат эмулятора — 0.3746066. Образ MKA пока не проверялся на физическом PicoCalc.']
    path=Path(__file__).with_name('HARNESS_RETENTION_RESULTS.md');path.write_text('\n'.join(lines)+'\n')
    p=Path(__file__).with_name('work-state.json');state=json.loads(p.read_text());counted=state.get('harness_retention_v1',{}).get('completed',False)
    state['phase']='harness_retention_v1_complete';state['all_own_jobs_complete']=True;state['free_language_coding_target_met']=False
    state['harness_retention_v1']={'completed':True,'selected_label':chosen,'selected_step':model['selected_step'],'results':results,
      'retention_guard_passed':summary['retention_guard_passed'],'artifact':str(root/'export/selected-budget/model.mkqb'),'report':str(path),'updates_each':1200}
    if smoke:state['harness_retention_v1']['native_boundary_smoke']=summary['native_boundary_smoke']
    if not counted:state['completed_training_runs']=state.get('completed_training_runs',0)+2;state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',0)+2400
    write(p,state);print(json.dumps({'selected':chosen,'fresh':results[chosen]['fresh'],'legacy':results[chosen]['legacy'],'report':str(path)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
