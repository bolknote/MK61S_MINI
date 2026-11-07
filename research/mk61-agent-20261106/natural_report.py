"""Honest fresh-language results and complete ISA retention after continuation."""
import argparse
import json
from pathlib import Path

from full_isa_common import read,write
from full_isa_vm import FullVM

LABELS=['baseline','full-best','protected-best','full-endpoint','protected-endpoint']


def pair(result):return [result['passed'],result['total']]


def compact(row):
    initial={r['id']:r['pass']for r in row['natural']['details']}
    return {'documented':row['main']['documented_instructions'],'isa_by_opcode':row['main']['by_opcode'],
      'isa_by_group':row['main']['by_group'],'programming':row['main']['by_kind']['programming'],
      'scientific':row['main']['by_kind']['numeric_synthesis'],'stateful':row['main']['by_kind']['interactive_game'],
      'fresh_language':pair(row['natural']),'fresh_by_group':row['natural']['by_group'],
      'observed_previous_153':pair(row['previous_natural_observed_retest']),
      'observed_user_27':pair(row['observed_user_reproductions']),'legacy_98':pair(row['legacy']),
      'tools':pair(row['tools']),'same_subset_without_tools':sum(initial[x['id']]for x in row['tools']['details']),
      'recovered_by_tools':sum(not initial[x['id']]and x['pass']for x in row['tools']['details']),
      'trace_requests':sum(bool(h.get('trace'))for x in row['tools']['details']for h in x['history']),
      'language_nll':row['language']['nll']}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root.resolve()
    reports={label:json.loads((root/'results'/(label+'.json')).read_text())for label in LABELS}
    train={arm:json.loads((root/arm/'training.json').read_text())for arm in ['full','protected']}
    assert all(x['completed']and x['steps']==3000 for x in train.values())
    assert train['full']['sample_plan_digest']==train['protected']['sample_plan_digest']
    final=json.loads((root/'final-export.json').read_text());chosen=final['selected_label'];selected=reports[chosen]
    manifest=json.loads((root/'export/selected-budget/manifest.json').read_text());prepared=json.loads((root/'prepared.json').read_text())
    local=json.loads((root/'local-verification.json').read_text());native=json.loads((root/'native-verification.json').read_text())
    context=json.loads((root/'context-verification.json').read_text());post=json.loads((root/'postflight.json').read_text())
    catalog=json.loads((root/'catalog.json').read_text());scores={k:compact(v)for k,v in reports.items()}
    vm=FullVM();tasks={t['id']:t for t in read(root/'observed-user-reproductions.jsonl')};sine=[]
    for row in selected['observed_user_reproductions']['details']:
        if row['id']not in ['user-repro:sin:RAD:22','user-repro:sin:DEG:22','user-repro:sin:GRAD:22']:continue
        task=tasks[row['id']];case=task['public_tests'][0]['segments'][0]
        state=vm.execute(row['code'],case['inputs'],angle=task['angle'])[0]if row['code']else None
        sine.append({'angle':row['angle'],'pass':row['pass'],'reply':row['reply'],
          'actual_X':state['raw']['X']if state else None,'expected_X':case['expected']['raw']['X']})
    baseline={r['id']:r for r in reports['baseline']['natural']['details']}
    improved=sum(not baseline[r['id']]['pass']and r['pass']for r in selected['natural']['details'])
    regressed=sum(baseline[r['id']]['pass']and not r['pass']for r in selected['natural']['details'])
    summary={'selected_label':chosen,'selected_step':manifest['selected_step'],'base_model':'full-isa-v1/protected-best step2000',
      'fresh_exam_used_for_selection':False,'results':scores,'sine22':sine,'fresh_paired_improvements':improved,
      'fresh_paired_regressions':regressed,'optimizer_updates_each':3000,'same_sample_plan':True,
      'sample_plan_digest':train['full']['sample_plan_digest'],'new_training_conditions':prepared['new_training_rows'],
      'fresh_conditions':prepared['fresh_language_rows'],'parameters':manifest['parameters'],'packed_bytes':manifest['packed_bytes'],
      'selected_packed_sha256':manifest['packed_sha256'],'cpu_b200_matches':[local['cpu_b200_matches'],local['compared']],
      'fp16_fp32_matches':[local['fp16_fp32_matches'],local['compared']],'context':context['scores'],
      'physical_picocalc_measured':False,'independent_human_programming_proven':False,'postflight':post}
    write(root/'comparison.json',summary)
    lines=['# 3M HEX: обычные русские запросы после полного набора команд','',
      f'Выбран **{chosen}**, шаг **{manifest["selected_step"]}** нового этапа. Начальные веса — `full-isa-v1/protected-best`, шаг 2000. '
      'Снимок выбран по новой валидации до открытия нового итогового набора.',
      '', '| Снимок | Новые русские /606 | Документированные /648 | Учебные вычисления /288 | Программы /135 | Прежние формулы /98 | Повтор старых русских /153 | Пользовательские /27 |',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in LABELS:
        s=scores[name];vals=[s['fresh_language'][0],s['documented']['passed'],s['scientific']['passed'],s['programming']['passed'],
          s['legacy_98'][0],s['observed_previous_153'][0],s['observed_user_27'][0]]
        lines.append('| '+name+' | '+' | '.join(map(str,vals))+' |')
    lines += ['', f'На новых 606 условиях исправлено {improved} прежних ошибок; испорчено ранее решавшихся: {regressed}. '
      'Старый экзамен команд, старые 153 русские задачи и запросы про синус уже были известны. В этом этапе они служат проверкой сохранения и исправления навыка, а не новым независимым экзаменом.',
      '', '## Что проверял новый набор','', '| Тип русской задачи | До | После |', '|---|---:|---:|']
    for group,value in selected['natural']['by_group'].items():
        b=reports['baseline']['natural']['by_group'][group]
        lines.append(f'| {group} | {b["passed"]}/{b["total"]} | {value["passed"]}/{value["total"]} |')
    lines += ['', 'Обучение и новые проверки используют разные полные шаблоны фраз и разные вводимые константы. В новом экзамене есть короткие запросы, словесные описания функций, символические формулы, двух- и трёхшаговые выражения и работа с текущим X. Функции и грамматика родственны обучению: это контролируемая синтетическая проверка переноса, а не широкий человеческий экзамен или доказательство произвольного программирования.',
      '', '## Синус 22','', '| Режим | HEX-вызов модели | X эмулятора | Эталон X | Успех |', '|---|---|---|---|---|']
    for x in sine:lines.append(f'| {x["angle"]} | `{x["reply"]}` | {x["actual_X"]} | {x["expected_X"]} | '+('да'if x['pass']else'нет')+' |')
    lines += ['', 'Этот запрос был известен заранее. Число 22 вошло в учебный диапазон констант, поэтому правильный ответ здесь показывает исправление пользовательского случая; обобщение отдельно оценивается на новых запросах.',
      '', '## Обучение и инструменты','',
      f'Добавлены {prepared["new_training_rows"]} проверенных условий. Новые эталоны сгенерированы по написанной русской грамматике и деревьям выражений, сверены со стандартной математикой и настоящим ядром МК-61 на шести наборах состояния. Новых API-вызовов большого учителя в этом этапе не было; веса начинаются с обученного им снимка, прежний корпус остаётся в повторении и вспомогательных планах.',
      f'Два варианта по 3000 обновлений, по {train["full"]["actual_examples"]:,} строк, одинаковый порядок примеров. В каждой группе из 128 строк: 64 новых языковых задания, 24 прежних формулы, 20 инструкционных, 8 программных, 4 инструментальных, 2 с продолжениями, 3 языковых отрывка и 3 вспомогательных плана. LR 2e-5, Q4 с первого обновления, контексты 512/1024/2048 с долями 85/10/5%.',
      'В full обучаются все входные эмбеддинги, в protected — только 37 строк компактного выхода. Остальные входные строки protected проверены побитно против начальных весов. Архитектура, русский входной словарь и 37 выходных токенов сохранены.',
      f'На 100 заранее выбранных новых условиях без инструментов выбранная модель решила {scores[chosen]["same_subset_without_tools"]}, с обратной связью — {scores[chosen]["tools"][0]}. Исправлено {scores[chosen]["recovered_by_tools"]}; запросов TRACE — {scores[chosen]["trace_requests"]}. Обратная связь использует только открытые случаи. Поиска программы или вызова учителя при исполнении нет.',
      'Свободные русские рассуждения не выводятся: исполняемый выход — полный HEX-вызов, TRACE или DONE. Учебные планы сами по себе не доказывают устойчивого режима рассуждений.',
      '', 'Контрольные точки новой валидации:','', '| Вариант | Шаг | Новые русские | Документированные | Прежние формулы |', '|---|---:|---:|---:|---:|']
    for arm,report in train.items():
        for row in report['history']:
            s=row['summary'];n=s['natural'];d=s['documented'];old=s['legacy']
            lines.append(f'| {arm} | {row["step"]} | {n["passed"]}/{n["total"]} | {d["passed"]}/{d["total"]} | {old["passed"]}/{old["total"]} |')
    lines += ['', '## Полный набор команд и контекст','',
      f'Документированные инструкции после продолжения: {scores[chosen]["documented"]["passed"]}/648. Все 256 значений HEX по-прежнему разрешены; 216 документированных вариантов команд проверяются отдельно от 40 служебных, ошибочных и недокументированных.',
      '', '| Контекст | Решено коротких /12 | Сохранено с посторонними заметками |', '|---|---:|---:|']
    for n,r in context['scores'].items():lines.append(f'| {n} | {r["solved_short"]} | {r["retained_long"]} |')
    info=native['models'][chosen];small=info['context1024']
    lines += ['', f'Точные Q4-веса повторно экспортированы и загружены без ошибки. Токены CPU/B200 совпали в {local["cpu_b200_matches"]}/{local["compared"]} пробах, FP16/FP32 хранение кеша — в {local["fp16_fp32_matches"]}/{local["compared"]}. Все пять экспортов проверены в частной копии нативного runtime, в пакетах с контекстом 2048 и 1024. Уникальных наборов весов: {local["unique_weight_payloads"]}; проб CPU без повторов одинаковых весов: {local["probes_excluding_identical_payloads"]}.',
      f'Параметров {manifest["parameters"]:,}, Q4 {manifest["packed_bytes"]:,} байт. Для нынешнего нативного FP32 KV пакет 1024 требует {small["native_cache_bytes"]:,} байт кеша; сумма MKA, KV и workspace — {small["package_plus_cache_and_workspace_bytes"]:,} байт ({small["package_plus_cache_and_workspace_bytes"]/1024**2:.2f} МиБ), без прочей памяти прошивки. При 2048 один кеш занимает 10 МиБ. Физический PicoCalc пока не измерялся.',
      '', '## Артефакты','',
      f'- [Новая выбранная Q4-модель]({root}/export/selected-budget/model.mkqb)',
      f'- [MKA, контекст 1024]({root}/export/selected-budget/model-context1024.mka)',
      f'- [Таблица входного протокола]({root}/export/selected-budget/prompt-template.txt)',
      f'- [Разрешённые выходные токены]({root}/export/selected-budget/output-token-ids.json)',
      f'- [Все результаты]({root}/comparison.json)',
      f'- [Первый этап: весь набор команд]({Path(__file__).with_name("FULL_ISA_RESULTS.md")})',
      '', f'SHA256 Q4: `{manifest["packed_sha256"]}`.',
      'Файлы исходного снимка и замороженных наборов не изменились. Наши GPU-контейнеры и контроллеры завершены. Продуктовый интерфейс в этом эксперименте не менялся; пакет предназначен для harness с указанным протоколом и маской выхода.']
    report_path=Path(__file__).with_name('NATURAL_LANGUAGE_RESULTS.md');report_path.write_text('\n'.join(lines)+'\n')
    opcode_lines=['# Сохранение полного набора команд после языкового этапа','', '| HEX | Команда | До /3 | После /3 |', '|---|---|---:|---:|']
    for op in catalog:
        if op['risk']!='documented':continue
        key=op['hex'];opcode_lines.append('| '+key+' | '+op['name'].replace('|','\\|')+f' | {scores["baseline"]["isa_by_opcode"][key]["passed"]} | {scores[chosen]["isa_by_opcode"][key]["passed"]} |')
    Path(__file__).with_name('NATURAL_LANGUAGE_OPCODE_RESULTS.md').write_text('\n'.join(opcode_lines)+'\n')
    state_path=Path(__file__).with_name('work-state.json');state=json.loads(state_path.read_text());counted=state.get('full_isa_natural_v1',{}).get('completed',False)
    state['phase']='full_isa_natural_v1_complete';state['all_own_jobs_complete']=True;state['free_language_coding_target_met']=False
    state['full_isa_natural_v1']={'completed':True,'selected_label':chosen,'selected_step':manifest['selected_step'],
      'fresh_language':scores[chosen]['fresh_language'],'documented':scores[chosen]['documented'],'observed_user_27':scores[chosen]['observed_user_27'],
      'sine22':sine,'report':str(report_path),'artifact':str(root/'export/selected-budget/model.mkqb'),'optimizer_updates_each':3000,
      'selected_packed_sha256':manifest['packed_sha256']}
    if not counted:
        state['completed_training_runs']=state.get('completed_training_runs',0)+2
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',0)+6000
    write(state_path,state)
    print(json.dumps({'selected':chosen,'fresh':scores[chosen]['fresh_language'],'groups':scores[chosen]['fresh_by_group'],
      'doc':scores[chosen]['documented'],'sine22':sine,'report':str(report_path)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
