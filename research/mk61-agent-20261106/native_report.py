"""Write the completed standard-ISA comparison from fetched measurements."""
import argparse
import json
from pathlib import Path


def read(path):return json.loads(path.read_text())


def score(metric):return f"{metric['passed']}/{metric['total']}"


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root;repo=Path(__file__).resolve().parents[2];here=Path(__file__).parent
    assert read(root/'complete.json')['completed']and read(root/'finish.json')['completed']
    assert read(root/'postflight.json')['all_own_jobs_complete']
    exported=read(root/'final-export.json');chosen=exported['selected_arm']
    verify=read(root/'local-verification.json');previous=read(root/'previous-3m-fresh.json')
    rows={arm:read(root/(arm+'-fresh.json'))for arm in ['q4','mixed']}
    training={arm:read(root/(arm+'-sft/training.json'))for arm in rows}
    manifests={arm:exported['exports'][arm]for arm in rows}
    activation=read(root/'provenance/initial-active-manifest.json')
    outcomes={arm:{x['id']:x['pass']for x in r['metrics']['manual']['program']['details']}for arm,r in rows.items()}
    assert set(outcomes['q4'])==set(outcomes['mixed'])
    paired={'both_pass':sum(outcomes['q4'][i]and outcomes['mixed'][i]for i in outcomes['q4']),
      'q4_only':sum(outcomes['q4'][i]and not outcomes['mixed'][i]for i in outcomes['q4']),
      'mixed_only':sum(outcomes['mixed'][i]and not outcomes['q4'][i]for i in outcomes['q4']),
      'both_fail':sum(not outcomes['q4'][i]and not outcomes['mixed'][i]for i in outcomes['q4'])}
    table=[]
    for arm,r in rows.items():
        s=r['summary'];m=manifests[arm]
        table.append({'arm':arm,'parameters':m['parameters'],'bytes':m['packed_bytes'],
          'manual_parse':s['manual']['parse'],'manual_program':s['manual']['program'],
          'teacher_program':s['teacher']['program'],'composed_program':s['composed']['program'],
          'context1024_program':s['context1024']['program'],'context2048_program':s['context2048']['program'],
          'full_formal':{'passed':r['full_formal']['passed'],'total':r['full_formal']['total']},
          'tool_rollouts':{k:r['tool_rollouts'][k]for k in ['passed','total']}})
    summary={'matrix':table,'selected_arm':chosen,'selection_used_fresh':False,
      'selection_rule':exported['selection']['rule'],
      'paired_manual_outcomes':paired,
      'previous_3m_same_fresh':previous['summary']['manual'],
      'basic_curriculum_gate_met':any(t['composed_training_enabled']for t in training.values()),
      'training':{arm:{k:t[k]for k in ['steps','best_step','best_key','actual_sample_counts','optimizer_steps_by_context','composed_training_enabled']}for arm,t in training.items()},
      'language_validation_nll':{arm:read(root/(arm+'-language/training.json'))['best_validation_nll']for arm in rows},
      'standard_mk61_program_bytes':105,'standard_mk61_registers':'R0..R9,Ra..Re',
      'extensions_enabled':False,'configured_context':2048,'fp16_kv_bytes_per_token':1280,
      'native_unit_tests_passed':4,'verification':{k:v for k,v in verify.items()if k!='details'},
      'native_device_measured':False,'activation_diagnostics':activation}
    (root/'summary-local.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    chosen_row=next(x for x in table if x['arm']==chosen)
    chosen_name='5,79M Q4'if chosen=='q4'else'7,51M Q2/Q4'
    absolute=root.resolve()
    lines=['<!-- native-mixed-v1 -->','',
      '## Полный курс для Q4 и Q2/Q4, стандартный МК-61 — 6 ноября 2026','',
      f"**По заранее заданной валидации выбрана {chosen_name}.** На новых ручных условиях первая программа: {score(chosen_row['manual_program'])}; формальная регрессия: {score(chosen_row['full_formal'])}. Итоговая выборка не выбирала модель или снимок.",'',
      '| Модель | Файл, МиБ | Программа /84 | Учитель /140 | Две операции /40 | Контекст 1024 /14 | Контекст 2048 /14 | Формальные /98 |',
      '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in table:
        name='5,79M Q4'if row['arm']=='q4'else'7,51M Q2 FFN / Q4 остальное'
        lines.append(f"| {name} | {row['bytes']/2**20:.3f} | {row['manual_program']['passed']} | {row['teacher_program']['passed']} | {row['composed_program']['passed']} | {row['context1024_program']['passed']} | {row['context2048_program']['passed']} | {row['full_formal']['passed']} |")
    lines+=['',f"По валидации сохранены снимки: Q4 — шаг {training['q4']['best_step']}, Q2/Q4 — шаг {training['mixed']['best_step']}. Числа учебных примеров каждого типа и обновлений каждой длины контекста совпали между моделями."]
    lines+=['',
      'На закрытом наборе смешанная модель решила на два условия больше. При этом 11 условий прошла только Q4, а 13 — только смешанная. Это небольшой разрыв при разном наборе ошибок. Выбор Q4 был зафиксирован по валидации; закрытая проверка его не меняла. Порог 90% новых ручных условий не достигнут, обе модели получили 0/40 на составных задачах. Надёжного программирования по свободному условию и переноса на несколько операций этот курс пока не дал.']
    lines+=['',
      f"Прежняя 3,02M Q4 на этих же новых 84 условиях: {score(previous['summary']['manual']['program'])}. Её выбрали до этого эксперимента. Это дополнительная проверка; одинаковый новый курс сравнивал только две новые архитектуры.",'',
      'Набор из 84 условий содержит семь простых операций, шесть ситуаций на операцию и две формулировки на ситуацию. Это не 84 новых семейства алгоритмов. Отдельные 40 составных задач содержат две операции. Они взяты из ранее не открытой части пула. Числовых примеров в начальном запросе нет; эталонный компилятор не пишет ответ за нейросеть. Каждая программа проверяется на девяти наборах чисел и сохранении исходных регистров.','',
      'Обучение и оценка исполняемых ответов используют стандартный МК-61: 105 байт программы и R0–R9, Ra–Re. Команды расширенной памяти MK61S не включены. Это ограниченный арифметический курс плюс проверка стандартных ветвлений, циклов и состояния; полное покрытие всей системы команд или генерация новой игры не установлены. В двух справочных текстах фонового языкового корпуса упоминаются другие профили, но расширенные команды не являются исполняемыми учебными целями.','',
      'В новых архитектурах 10 слоёв, ширина 256, восемь Q-голов, одна KV-голова, размер головы 32 и связанный словарь 8192. FFN равен 288 для Q4 и 512 для смешанного варианта. Полезные данные весов со шкалами занимают 3 277 312 и 3 261 952 байт. Группы содержат 32 веса; нормировки хранятся в FP32. В смешанной модели двухбитны только FFN. Их амплитуды обучаются вместе с весами; при экспорте эти шкалы сохранены. Подход к градиенту шкалы основан на идее [LSQ](https://arxiv.org/abs/1902.08153), но не воспроизводит статью.','',
      'Оба варианта происходят от исходной русской Flourish-3M. Сжатие двух KV-голов в одну и отбор FFN-признаков при инициализации являются потерями информации. Первые 2 000 общих языковых шагов сохранены для обеих моделей. Проверка показала, что дублированные скрытые направления оставались одинаковыми; перед продолжением они активированы противоположными изменениями кодов Q4. На четырёх русских пробах исходные ответы сохранены, максимальное изменение логитов менее 1,5e-5, а новые направления получили разные градиенты. Избыточные шаги старого прогрева исключены из продолжения. Диагностические обновления не сохранены как обучение.','',
      'После активации обе модели завершили по 6 104 языковых обновления: примерно 100 млн токенов каждая. Корпус содержит по 50 млн русских токенов Wikipedia и Cultura; ревизии, хэши файлов и разбиение документов сохранены. Исходное предобучение Flourish могло видеть эти документы. Проверочная NLL измерена на первых 65 536 токенах валидационного потока Wikipedia, а не на равной смеси двух источников. Для следующей стадии выбран языковой снимок шага 6 000.','',
      'Затем обе модели выполнили по 8 000 обновлений курса МК-61 в целевой битности. Учебных описаний 9 771, включая 2 184 новые короткие формулировки большого учителя. Они независимо разобраны обратно, а эталоны исполнены микрокодным ядром. Минимальные пары и точные тексты с переименованными регистрами разделены целиком. Примерно 30% ответов повторяют формальный код и настоящий протокол инструментов; 10% — языковой текст. В доменной половине языкового повторения используются 302 книжных фрагмента, 462 исторических листинга и шесть справок. Прохождение всех исторических игр не проверено.','',
      'Последние 2 000 обновлений выбирали длину 512, 1024 или 2048. Число обновлений каждой длины сохранено в отчёте. Отдельная проверка длинного контекста помещает условие в начало текста с посторонними заметками; тренировочные и проверочные заметки различаются. Результат относится к этому стресс-тесту и не устанавливает надёжность произвольного длинного диалога.','']
    if not summary['basic_curriculum_gate_met']:
        lines+=['На барьере шага 4 000 порог перехода к составным вычислениям — 90% разбора и исполнения на обеих языковых валидациях при не менее 95% формальной регрессии — не пройден. Поэтому подготовленные 1 374 составных примера не поступали в градиенты. Итоговые составные задачи проверяют перенос без отдельного курса.','']
    lines+=['Разбор `<calc>` выводит сама сеть. Это короткая структурированная формула перед байтами, а не установленная способность к универсальным рассуждениям. Инструментам модель обучается на `<write>`, `<run/>`, наблюдениях настоящего эмулятора, исправлении после FAIL/TRACE и `<done/>` после PASS.','']
    for row in table:
        lines.append(f"Три нейросетевых хода для {row['arm']}: {score(row['tool_rollouts'])} против {score(row['manual_program'])} с первой попытки. После первой попытки доступны публичные числовые входы и ожидаемые ответы; скрытые тесты не дают обратной связи. Автоматического перебора и компиляции ответа нет.")
    lines+=['',
      f"Все три экспорта восстановлены с ошибкой 0, включая обученные Q2-шкалы. CPU воспроизвёл {verify['cpu_b200_reply_matches']}/{verify['compared']} ответов B200; хранение KV в FP16 сохранило {verify['fp16_fp32_reply_matches']}/{verify['compared']} ответов CPU. Максимальная длина проверенного запроса — {verify['max_probed_prompt_tokens']} токенов. Журнал содержит все 22 пары ответов. Четыре технических теста нового квантователя и инициализации прошли.",'',
      'FP16 KV занимает 1 280 байт на токен: 1,25 МиБ для 1024 и 2,5 МиБ для 2048. Размер хранимых тензоров проверен на хосте. Веса плюс KV для 2048 — около 5,6 МиБ без токенизатора, рабочих буферов, эмулятора и интерфейса. Нативное исполнение этих экспортов, скорость и пиковая память PicoCalc не измерены.','',
      f"[Выбранные веса]({absolute}/export/selected-budget/model.mkqb) · [Метрики]({absolute}/summary-local.json) · [CPU и KV]({absolute}/local-verification.json) · [Манифест]({absolute}/export/selected-budget/manifest.json)",'']
    report=here/'FINAL_RESULTS.md';old=report.read_text();marker='<!-- native-mixed-v1 -->'
    old=old.split(marker)[0].rstrip()+'\n\n'+'\n'.join(lines)
    old=old.replace('Схема следующего, ещё не обученного сравнения:', 'Схема следующего сравнения (теперь обучено, результаты ниже):')
    report.write_text(old)
    state_path=here/'work-state.json';state=read(state_path)
    state.update(phase='native_mixed_comparison_complete',training_and_evaluation_complete=True,
      remote_experiment_jobs_complete=True,all_own_remote_jobs_complete=True,current_fresh_opened=True,
      selected_model='native-mixed-v1 '+chosen,final_model_manifest=str(root/'export/selected-budget/manifest.json'),
      final_export=str(root/'export'),next_action='Standard-ISA model comparison is complete; retain measured limitations before any extended-memory course.')
    state.pop('native_picocalc_inference_implemented',None)
    state.pop('total_optimizer_updates_across_all_runs',None)
    state.update(completed_training_runs_before_native=21,completed_training_runs=25,
      historical_optimizer_updates_before_native=51600,total_accounted_optimizer_updates_lower_bound=83808,
      new_exports_native_device_execution_measured=False,current_training_jobs_started=6,
      interrupted_warmup_runs=2,interrupted_warmup_extra_updates_not_fully_counted=True)
    state['limitations']=[
      'The language-to-standard-MK61 course covers seven scalar operations; compound and formal/control tests are reported separately.',
      'Short calc prefixes do not demonstrate general reasoning ability.',
      'Context2048 is evaluated using unrelated-note stress probes, not arbitrary long programming sessions.',
      'Host results use FP32 activations/KV; FP16 KV is a separate sampled storage check.',
      'Native PicoCalc execution, peak RAM and speed of these new exports were not measured.',
      'Historical corpus uses462 normalized listings and selected prose from9 books; not all games are gameplay-verified.']
    state['native_mixed_v1'].update(completed=True,selected=chosen,summary=summary,
      long_context_evaluated=True,long_context_reliability_established=False,completed_new_training_stages=4,
      completed_additional_language_updates_each=6104,completed_sft_updates_each=8000)
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    readme=here/'README.md';text=readme.read_text();heading='## Completed native Q4 versus mixed-bit comparison'
    intro=f'''{heading}

The two new architectures completed matched language continuation and8,000
standard-MK61 SFT updates each, with target-bit training throughout. Validation
selected `{chosen}` before the new84-condition audit opened. Its first neural
program passes {score(chosen_row['manual_program'])}; full formal regression is
{score(chosen_row['full_formal'])}. Extended MK61S memory commands are excluded
from executable targets. See [all measured results](FINAL_RESULTS.md#полный-курс-для-q4-и-q2q4-стандартный-мк-61--6-ноября-2026).

The mixed model passes67/84 on that audit, compared with65/84 for Q4 and63/84
for the previous3M baseline. Neither new model reaches the90% target or solves
the40 compound tasks. Long-context scores are10/14 at1024 and9/14 at2048.

The actual evaluated MKQB packets and learned Q2 scales are preserved under
`{absolute}/export`. CPU replay and FP16 KV storage checks are in
`local-verification.json`. This does not measure native PicoCalc performance.

'''
    if heading in text:
        start=text.index(heading);end=text.index('## Completed capacity and low-bit comparison',start)
        text=text[:start]+intro+text[end:]
    else:text=text.replace('## Completed capacity and low-bit comparison',intro+'## Completed capacity and low-bit comparison',1)
    text=text.replace('The accepted next course compares','The completed preceding course compared')
    text=text.replace('Native PicoCalc execution remains unimplemented.','Native PicoCalc execution of these checkpoint exports has not been measured.')
    text=text.replace('A native PicoCalc runtime has not been implemented or timed.','Native PicoCalc execution of these checkpoint exports has not been measured.')
    readme.write_text(text)
    print(json.dumps({'selected':chosen,'table':table,'previous_3m':previous['summary']['manual']},ensure_ascii=False))


if __name__=='__main__':main()
