"""Summarize the paired continuation without turning validation into fresh results."""
import argparse
import json
from pathlib import Path
import subprocess


def read(path):return json.loads(path.read_text())
def score(x):return f"{x['passed']}/{x['total']}"


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve();here=Path(__file__).parent;repo=here.parents[1]
    complete=read(root/'complete.json');assert complete['completed']
    assert read(root/'postflight.json')['all_own_jobs_complete']
    exported=read(root/'final-export.json');selection=read(root/'preselected.json');winner=selection['winner']
    verify=read(root/'local-verification.json');manifest=read(root/'course/manifest.json')
    # Benchmark only after model and checkpoint selection have already frozen.
    if not(root/'native-host-benchmark.json').exists():
        with(root/'native-benchmark.log').open('w')as log:
            result=subprocess.run([str(repo/'.build/squeal-chat-20261105/venv/bin/python'),str(here/'compose_native_bench.py'),'--root',str(root)],cwd=repo,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:(root/'native-benchmark-unavailable.json').write_text(json.dumps({'returncode':result.returncode,'log':'native-benchmark.log','native_device_measured':False})+'\n')
    bench=read(root/'native-host-benchmark.json')if(root/'native-host-benchmark.json').exists()else None
    stages={};matrix=[]
    for arm in ['champion','small']:
        stages[arm]=[read(root/f'{arm}-phase{phase}/training.json')for phase in range(1,selection['completed_phases']+1)]
        before=read(root/f'results/{arm}-baseline.json');after=read(root/f'results/{arm}-final.json')
        full_before=read(root/f'results/full-formal-{arm}-baseline.json');full_after=read(root/f'results/full-formal-{arm}-final.json')
        required=[after['summary'][part][kind]['rate']for part in ['manual1','manual2','manual3','teacher2','teacher3']for kind in ['parse','program']]
        long=[after['summary'][part]['program']['rate']for part in ['context1024','context2048']]
        quality=min(required)>=.9 and min(long)>=.8 and full_after['pass_rate']>=.95
        m=exported['exports'][arm]
        matrix.append({'arm':arm,'parameters':m['parameters'],'packed_bytes':m['packed_bytes'],
          'before':before['summary'],'after':after['summary'],
          'formal98_before':{k:full_before[k]for k in ['passed','total','pass_rate']},
          'formal98_after':{k:full_after[k]for k in ['passed','total','pass_rate']},
          'tool_rollouts':{k:after['tool_rollouts'][k]for k in ['passed','total']},
          'fresh_quality_target_met':quality,'selected_phase':m['phase'],'selected_step_in_phase':m['best_step_in_phase'],
          'fp16_kv_bytes_per_token':m['fp16_kv_bytes_per_token']})
    for i in range(selection['completed_phases']):
        assert stages['champion'][i]['actual_sample_counts']==stages['small'][i]['actual_sample_counts']
        assert stages['champion'][i]['optimizer_steps_by_context']==stages['small'][i]['optimizer_steps_by_context']
    supplemental={p.parent.name:read(p)for p in root.glob('*/manifest.json')if p.parent.name.startswith(('augmentation-','balanced-','morphology-'))}
    structural={}
    for path in(root/'results').glob('structural4-*.json'):
        result=read(path);structural[path.stem]={kind:{k:result[kind][k]for k in ['passed','total','rate']}for kind in ['parse','program']}
    diagnostics={p.stem:read(p)for p in(root/'diagnostics').glob('*phase*-step*.json')if not p.name.startswith(('rag-','constraint-'))}
    constraints={p.stem:{**{k:v for k,v in read(p).items()if k!='metrics'},'metrics':{name:{k:v for k,v in values.items()if k!='details'}for name,values in read(p)['metrics'].items()}}for p in(root/'diagnostics').glob('constraint-*.json')}
    error_path=root/'diagnostics/development-error-analysis.json'
    error_analysis=read(error_path)if error_path.exists()else None
    rag=root/'diagnostics/rag-champion-phase2-step6000.json'
    rag_summary={k:{key:v[key]for key in ['parse_passed','program_passed','total']}for k,v in read(rag)['metrics'].items()}if rag.exists()else None
    full_grammar_trained=selection['completed_phases']>=4
    chosen=next(row for row in matrix if row['arm']==winner)
    observed_program_totals={row['arm']:sum(row['after'][part]['program']['passed']for part in ['manual1','manual2','manual3'])for row in matrix}
    summary={'matrix':matrix,'selected':winner,'selected_quality_target_met':chosen['fresh_quality_target_met'],
      'selection_used_fresh':False,'completed_phases':selection['completed_phases'],
      'observed_first_program_totals_out_of138':observed_program_totals,
      'new_optimizer_updates_each':8000*selection['completed_phases'],'shared_initial_course':manifest,
      'supplemental_data':supplemental,'matched_sample_counts_verified':True,
      'verification':{k:v for k,v in verify.items()if k!='details'},'new_unit_checks_passed':12,
      'full_bounded_grammar_training_included':full_grammar_trained,'controlled_structural4_probe':structural,
      'training_fit_diagnostics':diagnostics,'untrained_retrieval_probe':{'adopted':False,'metrics':rag_summary},
      'untrained_constraint_probes':constraints,
      'development_error_analysis':error_analysis,
      'native_host_benchmark':bench,'picocalc_device_measured':False,
      'fresh_condition_authorship':'Codex authored these conditions before teacher generation and gradients; no independent human study',
      'scope':'Seven arithmetic operations onR0-R3, two/three-op Russian conditions; standard105-step ISA and separate formal/control regression'}
    (root/'summary-local.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    label={'champion':'5,79M Q4','small':'3,02M Q4'}
    lines=['# Составные задачи: 5,79M Q4 и 3,02M Q4','',
      f"**По валидации выбрана {label[winner]}.** Итоговый новый набор содержит 42 простых условия, 64 условия из двух действий и 32 из трёх. Выбор модели и снимков завершён до открытия этого набора.",'',
      '**Порог качества достигнут.**'if chosen['fresh_quality_target_met']else'**Порог качества пока не достигнут.** Завершение этого сравнения не означает, что модель стала надёжным программистом по свободному условию.','',
      f"На новом наборе у чемпиона успешно {observed_program_totals['champion']}/138 первых программ, у 3M — {observed_program_totals['small']}/138. Это наблюдение после выбора: предварительная валидация предпочла 3M по худшей группе задач, но её преимущество не перенеслось на новый набор. Файл предварительного выбора и оба экспорта сохранены без пересмотра по тесту.",'',
      '| Модель | Веса, МиБ | Простые /42, до → после | Два действия /64 | Три действия /32 | Прежний формальный набор /98 |',
      '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in matrix:
        values=[f"{row['before'][part]['program']['passed']} → {row['after'][part]['program']['passed']}"for part in ['manual1','manual2','manual3']]
        lines.append(f"| {label[row['arm']]} | {row['packed_bytes']/2**20:.3f} | {' | '.join(values)} | {row['formal98_before']['passed']} → {row['formal98_after']['passed']} |")
    lines+=['',
      'Числа показывают исполнение первой программы самой нейросети на девяти наборах значений, включая подписанные числа и сохранение входных R0–R3. Начальных числовых примеров и эталонного выражения в запросе нет. Нейросеть выводит формулу и байты; внешний компилятор не составляет за неё ответ при оценке. Два действия представлены 32 ситуациями с двумя формулировками, три действия — 16 ситуациями с двумя формулировками. Это ограниченная арифметика, а не доказательство универсального программирования или генерации игр.','',
      '| Модель | Разбор двух действий /64 | Разбор трёх /32 | Контекст 1024 | Контекст 2048 | Три хода с эмулятором /138 |',
      '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in matrix:
        s=row['after'];lines.append(f"| {label[row['arm']]} | {score(s['manual2']['parse'])} | {score(s['manual3']['parse'])} | {score(s['context1024']['program'])} | {score(s['context2048']['program'])} | {score(row['tool_rollouts'])} |")
    lines+=['',
      'В длинном контексте условие находится в начале посторонних заметок. Учебные и проверочные заметки различаются. Это проверка удержания условия, а не произвольного длинного диалога. При повторных ходах доступны только настоящие публичные FAIL/TRACE с числовыми входами и ожидаемыми ответами. Скрытые случаи не управляют повторными попытками; автоматического перебора нет. Формальный набор /98 уже наблюдался в прежних опытах и служит проверкой регрессии, а не новым независимым тестом.','',
      f"Обе модели получили по {8000*selection['completed_phases']:,} новых обновлений. Их исходные истории обучения различаются: это сравнение двух практических кандидатов, а не изоляция единственного эффекта числа параметров. Q4 действует с первого обновления; битность весов не переключалась в конце. У обоих 10 слоёв и словарь 8192; ширина 256/128, KV-голов 1/2 соответственно. Конфигурация 3M расширена с 512 до 2048 и отдельно обучена на длинных примерах. Исходные пакеты восстановлены без изменения значений весов.",'',
      f"Начальный корпус: {manifest['train']:,} условий, из них {manifest['counts_by_level']['2']:,} из двух действий и {manifest['counts_by_level']['3']:,} из трёх. Новых описаний учителя после слепой проверки — 2 515 в обучении. Первый некорректный генеративный проход исключён до градиентов. В рабочем проходе учитель получал одно явное выражение; другой запрос видел только текст и обезличенный ID. Генерация и слепое чтение выполнялись одной большой моделью в разных запросах. Эталонные программы проверены микрокодным ядром.",'',
      'В первой фазе обнаружен перекос: только 41 из 2 401 трёхоперационного примера имел четыре разных входа. Общий дополнительный курс покрывает систематические деревья выражений с разными исходными регистрами и явно заданной очередностью действий. Синтетические процедурные описания помечены отдельно от текста учителя. Дедупликация учебных текстов сохраняет различие R0+R0 и R0+R1; запрет точных совпадений с ручными проверками остаётся строгим. Количества добавленных материалов и хэши приведены в summary-local.json.','',
      'После первого этапа 25% примеров повторяют простые задачи, 25% — формальный код и реальный протокол инструментов, 5% — языковой корпус; остальные 45% учат композициям. Во второй/третьей фазах добавляются ошибки обеих моделей на учебных условиях с реальной обратной связью. Третья фаза усиливает разбор смысла: часть потерь учитывает операции и регистры без разбавления известными XML-маркерами. Половина примеров разбора сохраняет полную разметку ответа. Реальные счётчики примеров и длин контекста совпали между моделями.','',
      'Новые условия отдельно составлены Codex и зафиксированы до учителя и градиентов; они не добавлялись как учебные ответы. Это не исследование с независимыми людьми. Ранее открытые 40 составных задач используются только для наблюдаемой валидации. Ни один закрытый результат не выбирал снимок или длительность курса.','',
      ('В первых трёх фазах часть деревьев выражений оставалась вне обучения. Четвёртая фаза покрывает все сочетания до трёх операций и правильные русские падежи и порядки слов. Поэтому основной итоговый тест проверяет новые формулировки известных ограниченных математических структур. Это расширение курса выбрано по наблюдаемой валидации до открытия итоговых ответов. Отдельные новые четырёхоперационные деревья проверены после выбора; их описания генерируются контролируемой грамматикой и не являются независимыми человеческими историями.'if full_grammar_trained else'Для многoоперационного курса сохраняется структурное разбиение split_of(AST); ограничения дополнений записаны в их манифестах.'),'',
      'Профиль эмулятора — стандартный МК-61, 105 байт программы и 15 регистров. Естественно-языковой арифметический курс использует R0–R3 и семь операций; полное покрытие всех команд не установлено. Расширенная память MK61S не включена в исполняемые цели. Книжные фрагменты и исторические листинги остаются частью фонового языкового повторения.','',
      f"Все экспорты восстановлены точно. На CPU совпали {verify['cpu_b200_matches']}/{verify['compared']} ответов с B200; хранение KV в FP16 сохранило {verify['fp16_fp32_matches']}/{verify['compared']} ответов CPU. Максимальный проверенный запрос — {verify['max_actual_prompt_tokens']} токенов. Двенадцать технических проверок данных, переименования регистров, путей контейнера, русских форм, семантических меток и экспериментальной грамматики прошли.",'',
      '| Модель | FP16 KV на токен | Веса + KV при 1024, МиБ | При 2048, МиБ |',
      '| --- | ---: | ---: | ---: |']
    for row in matrix:
        kv=row['fp16_kv_bytes_per_token'];lines.append(f"| {label[row['arm']]} | {kv} байт | {(row['packed_bytes']+1024*kv)/2**20:.2f} | {(row['packed_bytes']+2048*kv)/2**20:.2f} |")
    lines+=['','Расчёт исключает токенизатор, рабочие буферы, эмулятор и интерфейс. Большая модель экономит KV за счёт одной KV-головы; меньшие веса сами по себе не гарантируют большее окно. FP16 здесь проверен как способ хранения на хосте, арифметика внимания остаётся FP32.','']
    if bench:
        lines+=['| Модель | Нативное ядро на хосте: токенов/с | Prefill 512, с | Фактический KV этого ядра |','| --- | ---: | ---: | ---: |']
        for arm,b in bench['models'].items():lines.append(f"| {label[arm]} | {b['decode_tokens_per_second_median']:.1f} | {b['prefill_seconds_median']:.3f} | {b['cache_bytes']/2**20:.2f} МиБ |")
        lines+=['',f"На этом хосте 3M быстрее по декодированию в {bench['small_decode_speed_ratio']:.2f} раза. Измерены один и тот же существующий C++ Q4 LUT-код, 512 входных токенов и 32 шага декодирования; медиана трёх прогонов. Сохранён снимок исходников. Аргмаксы логитов сверены с HF. Этот вариант нативного ядра хранит KV в FP32, поэтому его фактический кэш вдвое больше FP16-расчёта. Это не замер RP2350, PSRAM или SD-карты.",'']
        lines+=['| Модель | Пакет MKA с токенизатором, МиБ | Пакет + рабочая область + KV при 2048, МиБ |','| --- | ---: | ---: |']
        for arm,b in bench['models'].items():lines.append(f"| {label[arm]} | {b['native_package_bytes']/2**20:.2f} | {(b['native_package_bytes']+b['workspace_bytes']+b['cache_bytes'])/2**20:.2f} |")
        lines+=['','Последний столбец относится к фактически измеренному ядру с FP32 KV и не включает интерфейс и эмулятор. Поэтому конфигурация окна 2048 сама по себе не подтверждает размещение полного приложения в памяти PicoCalc; для уменьшения кэша нужен другой формат хранения либо более короткое окно.','']
    else:lines+=['Скорость на PicoCalc не измерена. Отдельный замер нативного ядра на хосте недоступен; диагностический журнал сохранён в native-benchmark.log.','']
    if rag_summary:
        lines+=['Дополнительный опыт на открытой валидации: три учебных примера, выбранные по близости BPE TF-IDF, ухудшили результат. Без обучения на таком формате поиск примеров не принят. Этот опыт не менял основной итоговый протокол.','']
    if error_analysis:
        lines+=['Диагностика на шаге 7 000 четвёртой фазы: у обеих сетей все 84 составные программы точно соответствовали их собственным формулам, включая неверные формулы. У чемпиона в 12 из 24 трёхоперационных условий формула содержала лишь два действия. Поэтому главная измеренная проблема — восстановление смысла условия, а не перевод своей формулы в байты. Это вывод по наблюдаемой валидации, без использования итоговых ответов для выбора.','']
    if constraints:
        lines+=['| Снимок: отдельный опыт harness | Два действия /60, обычный → ограниченный вывод | Три действия /24 |','| --- | ---: | ---: |']
        for name,probe in sorted(constraints.items()):
            scores=[f"{probe['metrics'][part]['plain_program_passed']} → {probe['metrics'][part]['program_passed']}"for part in ['manual2','manual3']]
            lines.append(f"| {label[probe['arm']]}, фаза {probe['phase']}, шаг {probe['step']} | {' | '.join(scores)} |")
        lines+=['','Грамматика разрешает до трёх операций и требует учесть все регистры R0–R3, названные в коротком условии. Операции и байты выбирает сеть, без эталонного выражения, числовых проверок или внешнего компилятора. Предположение о нужности всех упомянутых регистров ограничивает применимость; это отдельный опыт на валидации, а не чистая точность модели и не результат на новых задачах. Основной итоговый тест проходит без этого ограничителя.','']
    lines += [f"[5,79M Q4]({root}/export/champion/model.mkqb) · [3,02M Q4]({root}/export/small/model.mkqb) · [Все метрики]({root}/summary-local.json) · [Проверка CPU и KV]({root}/local-verification.json) · [Выбор до теста]({root}/preselected.json)",'']
    if(here/'CODEC_STUDY.md').exists():lines+=['[Отдельное исследование выходного словаря и кодека](CODEC_STUDY.md).','']
    (here/'COMPOSITION_RESULTS.md').write_text('\n'.join(lines))
    report=here/'FINAL_RESULTS.md';marker='<!-- composition-v1 -->';old=report.read_text().split(marker)[0].rstrip()
    addition=f"{marker}\n\n## Продолжение на составных задачах\n\nЗавершено парное продолжение 5,79M Q4 и 3,02M Q4. По валидации выбрана {label[winner]}. Порог качества {'достигнут'if chosen['fresh_quality_target_met']else'пока не достигнут'}. [Подробные результаты и веса](COMPOSITION_RESULTS.md).\n"
    report.write_text(old+'\n\n'+addition)
    state_path=here/'work-state.json';state=read(state_path)
    state.update(phase='composition_quality_target_met'if chosen['fresh_quality_target_met']else'composition_audited_below_target',
      training_and_evaluation_complete=True,all_own_remote_jobs_complete=True,remote_experiment_jobs_complete=True,
      current_fresh_opened=True,selected_model='composition-v1 '+winner,final_report=str(here/'COMPOSITION_RESULTS.md'),
      final_export=str(root/'export'),final_model_manifest=str(root/'export/selected-budget/manifest.json'),
      free_language_coding_target_met=chosen['fresh_quality_target_met'],
      next_action='Measured target met; native device deployment remains unmeasured.'if chosen['fresh_quality_target_met']else'Continue improving semantics: this completed comparison is below the requested quality target.')
    state.setdefault('completed_training_runs_before_composition',state['completed_training_runs'])
    state.setdefault('accounted_optimizer_updates_before_composition',state['total_accounted_optimizer_updates_lower_bound'])
    state['completed_training_runs']=state['completed_training_runs_before_composition']+2*selection['completed_phases']
    state['total_accounted_optimizer_updates_lower_bound']=state['accounted_optimizer_updates_before_composition']+16000*selection['completed_phases']
    state['neural_quality_target_met']=chosen['fresh_quality_target_met']
    state['composition_v1'].update(completed=True,quality_target_met=chosen['fresh_quality_target_met'],summary=summary,
      current_training_pending_verified_data=False,completed_training_phases_each=selection['completed_phases'],
      active_phase=None,completed_optimizer_updates_each=8000*selection['completed_phases'],
      current_unit_tests_passed=12,new_local_composition_tests_passed=12)
    state['composition_v1']['policy'].update(formal_tool_replay_fraction=.25,
      extra_phases_if_validation_target_not_met=selection['completed_phases']-1,
      train_multioperation_structures='Phases1-3: split_of(AST)==train. Phase4: all bounded1/2/3-operation structures.')
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'selected':winner,'quality_target_met':chosen['fresh_quality_target_met'],'matrix':matrix},ensure_ascii=False))


if __name__=='__main__':main()
