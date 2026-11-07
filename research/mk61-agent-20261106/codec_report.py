"""Report matched HEX/H32 learning without using the closed audit for checkpoint selection."""
import argparse
import json
from pathlib import Path
import statistics

from codec_common import ARMS,MODES,Protocol,read
from codec_stats import comparison
from course_common import answer


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve();here=Path(__file__).resolve().parent
    assert json.loads((root/'complete.json').read_text())['completed']
    assert json.loads((root/'postflight.json').read_text())['all_own_jobs_complete']
    selection=json.loads((root/'preselected.json').read_text());exported=json.loads((root/'final-export.json').read_text())
    verify=json.loads((root/'local-verification.json').read_text());native=json.loads((root/'native/verification.json').read_text())
    analysis_path=root/'posthoc-encoding-analysis.json';encoding_analysis=json.loads(analysis_path.read_text())if analysis_path.exists()else None
    tasks=[t for level in [1,2,3]for t in read(root/f'fresh{level}.jsonl')];results={};secondary={};baselines={};training={};paired={}
    def rows(result):return [r for part in ['manual1','manual2','manual3']for r in result['metrics'][part]['program']['details']]
    for arm in ARMS:
        baselines[arm]=json.loads((root/f'results/{arm}-hex-baseline.json').read_text())
        for mode in MODES:
            name=arm+'-'+mode;results[name]=json.loads((root/f'results/{name}-endpoint.json').read_text())
            secondary[name]=json.loads((root/f'results/{name}-best.json').read_text())
            training[name]=json.loads((root/name/'training.json').read_text())
        paired[arm]=comparison(tasks,rows(results[arm+'-hex']),rows(results[arm+'-h32']))
    first=next(iter(training.values()))
    assert all(r['sample_plan_digest']==first['sample_plan_digest']and r['actual_sample_counts']==first['actual_sample_counts']and r['optimizer_steps_by_context']==first['optimizer_steps_by_context']for r in training.values())
    compact={}
    for name,result in results.items():
        r=rows(result);arm,mode=name.split('-');m=exported['exports'][name]['endpoint']
        compact[name]={'programs':{part:result['summary'][part]['program']for part in ['manual1','manual2','manual3','context1024','context2048']},
          'passed':sum(x['pass']for x in r),'total':len(r),'macro':sum(result['summary']['manual'+str(i)]['program']['rate']for i in [1,2,3])/3,
          'valid_program_calls':sum(x['valid_program_call']for x in r),'codec_errors':sum(x['codec_error']is not None for x in r),
          'generated_tokens_mean':statistics.mean(x['generated_tokens']for x in r),'formal98':result['full_formal']['passed'],
          'tool_rollouts':result['tool_rollouts']['passed'],'public_language_nll':result['public_language']['nll'],
          'parameters':m['parameters'],'packed_bytes':m['packed_bytes'],'output_rows':m['output_rows_computed']}
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(root/'export/endpoint/small-h32/hf',local_files_only=True,trust_remote_code=False)
    book=json.loads((root/'codebook-32.json').read_text());lengths={}
    for mode in MODES:
        p=Protocol(mode,book);lengths[mode]={'reference_full_answer_tokens':sum(len(tokenizer.encode(p.encode_text(answer(t)),add_special_tokens=False))for t in tasks),
          'reference_body_tokens':sum(len(tokenizer.encode(p.body(t['reference_code']),add_special_tokens=False))for t in tasks)}
    summary={'primary_endpoints':compact,'paired_primary_comparisons':paired,'reference_serialization_lengths':lengths,
      'secondary_best_steps':{n:r['best_step']for n,r in training.items()},'sample_plans_equal_all_four':True,
      'sample_plan_digest':first['sample_plan_digest'],'new_optimizer_updates_each':8000,'effective_batch':128,
      'new_semantic_examples_seen_each':8000*128,'source_initialization_shared_within_each_architecture':True,
      'original_russian_input_vocabulary':8192,'added_huffman_symbols':32,'total_embedding_rows':8224,
      'new_audit_counts':{str(i):len([t for t in tasks if t['level']==i])for i in [1,2,3]},
      'new_fresh_used_for_selection':False,'independent_human_study':False,'native_picocalc_measured':False,
      'posthoc_own_formula_encoding':encoding_analysis,
      'verification':{k:v for k,v in verify.items()if k not in ['details','exports']},
      'native':{k:v for k,v in native.items()if k not in ['models','source_files_sha256']}}
    (root/'summary-local.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    labels={'champion':'5,80M','small':'3,02M'}
    lines=['# HEX и Хаффман-32: четыре одинаковых продолжения в Q4','',
      'Основное сравнение — последние снимки после 8 000 обновлений, независимо от результатов нового набора. Для каждого размера HEX и H32 стартовали из одних весов, получили одинаковые смысловые примеры, перестановки регистров и длины контекста. Хэши всей последовательности выборки совпали у всех четырёх вариантов.','',
      '| Модель | Выход | Простые /28 | Два действия /64 | Три /48 | Всего /140 | Среднее трёх долей |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for arm in ARMS:
        for mode in MODES:
            r=compact[arm+'-'+mode];scores=[str(r['programs']['manual'+str(i)]['passed'])for i in [1,2,3]]
            lines.append(f"| {labels[arm]} | {mode.upper()} | {' | '.join(scores)} | {r['passed']} | {100*r['macro']:.1f}% |")
    lines+=['','Доли — исполнение первой программы нейросети на девяти наборах значений, включая отрицательные входы и сохранность R0–R3. Начальные числовые примеры и эталонная формула скрыты от модели. Декодер H32 только восстанавливает байты; внешний компилятор не составляет программу по формуле. Модель сама выдаёт и `<calc>`, и программу.','',
      'На конечном шаге 3M немного выше чемпиона в обеих кодировках. При выборе снимков по валидации HEX даёт41/140 у3M и40/140 у чемпиона; H32 —37/140 и38/140 соответственно. Устойчивое преимущество размера по этим небольшим различиям не установлено. Истории обучения архитектур различаются: это сравнение двух практических кандидатов, а не изоляция одного числа параметров.','']
    if encoding_analysis:
        lines+=['У трёх вариантов все140 программ точно совпали с каноническим кодом собственных предсказанных формул; у3M H32 —139/140. При этом большинство этих формул неверно передаёт исходное условие. Диагностика указывает на восстановление смысла как основное узкое место. Она выполнена после выбора, без новых градиентов.','']
    for arm in ARMS:
        p=paired[arm];lo,hi=p['macro_delta_bootstrap95'];lines.append(f"Разница H32 − HEX для {labels[arm]}: **{100*p['macro_delta_h32_minus_hex']:+.1f} п.п.**, описательный 95%-интервал по сценариям [{100*lo:+.1f}; {100*hi:+.1f}].")
    lines+=['','Интервал построен 10 000 повторными выборками внутри каждого уровня: парные формулировки составных задач остаются вместе. Общие математические семейства дополнительно не кластеризованы. Условия составлены Codex, не независимыми людьми; вывод относится к этому ограниченному набору.','',
      '| Модель | Выход | Корректных вызовов /140 | Три хода с эмулятором /140 | Формальный набор /98 | Контекст 1024 | Контекст 2048 |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for arm in ARMS:
        for mode in MODES:
            r=compact[arm+'-'+mode];long=[f"{r['programs'][part]['passed']}/{r['programs'][part]['total']}"for part in ['context1024','context2048']]
            lines.append(f"| {labels[arm]} | {mode.upper()} | {r['valid_program_calls']} | {r['tool_rollouts']} | {r['formal98']} | {' | '.join(long)} |")
    lines+=['','Повторные ходы получают только настоящие публичные FAIL/TRACE. Скрытые случаи не управляют попытками, автоматического поиска программ нет. Формальный набор уже наблюдался в прежних опытах и служит проверкой регрессии. В длинном контексте условие находится перед посторонними заметками; это проверка удержания условия, а не свободного длинного диалога.','',
      '| Модель | Исходный HEX: всего /140 | После HEX | После H32 |','| --- | ---: | ---: | ---: |']
    for arm in ARMS:lines.append(f"| {labels[arm]} | {sum(x['pass']for x in rows(baselines[arm]))} | {compact[arm+'-hex']['passed']} | {compact[arm+'-h32']['passed']} |")
    lines+=['','Отдельно сохранены лучшие по валидации снимки. Это вторичное сравнение: основной результат выше всегда относится к фиксированному шагу 8 000. Все вторичные снимки выбраны до открытия новых условий. Валидация включает ранее открытые 138 условий, которые не добавлялись как учебные ответы.','',
      '| Модель | Выход | Выбранный шаг | Новые задачи /140 |','| --- | --- | ---: | ---: |']
    for arm in ARMS:
        for mode in MODES:
            name=arm+'-'+mode;lines.append(f"| {labels[arm]} | {mode.upper()} | {training[name]['best_step']} | {sum(x['pass']for x in rows(secondary[name]))} |")
    saving=1-lengths['h32']['reference_full_answer_tokens']/lengths['hex']['reference_full_answer_tokens']
    lines+=['',f"Для одних и тех же эталонных ответов новый набор требует {lengths['hex']['reference_full_answer_tokens']:,} токенов в HEX и {lengths['h32']['reference_full_answer_tokens']:,} в H32, экономия {100*saving:.1f}% всего ответа. В этих числах сохранены обычные XML-маркеры и промежуточная формула, EOS не учитывается. Выигрыш на теле программы больше выигрыша на полном ответе.",'',
      '| Модель | Выход | Параметров | MKQB, МиБ | Выходных строк | NLL русского фона |','| --- | --- | ---: | ---: | ---: | ---: |']
    for arm in ARMS:
        for mode in MODES:
            r=compact[arm+'-'+mode];lines.append(f"| {labels[arm]} | {mode.upper()} | {r['parameters']:,} | {r['packed_bytes']/2**20:.3f} | {r['output_rows']} | {r['public_language_nll']:.4f} |")
    lines+=['','Обе версии каждого размера имеют одни и те же 32 дополнительные строки эмбеддингов: архитектура и число параметров внутри пары равны. Первоначальные 8192 русских токена сохранили номера и сегментацию, общий словарь содержит 8224 строки. При программировании вычисляются 54/68 выходных строк, при языковом повторении — прежние 8192. NLL измерена на одинаковых 8192 токенах публичного языкового корпуса. Это индикатор языковой регрессии, а не прямое измерение понимания русского.','',
      'Таблица Хаффмана построена только по прежнему учебному материалу и зафиксирована до новых градиентов. Все 256 байтов, включая адреса и операнды, представимы; новые или редкие байты не заменяются частыми. Исполняемая программа МК-61 остаётся той же длины в байтах. Укорочена её запись для нейросети.','',
      'На первом этапе 1 000 обновлений половина примеров обучает переводу заданной формулы в код, 25% — формальным задачам и инструментам, 10% — языку, 15% — простым условиям. Затем: 45% составных условий, 25% простых, 25% формального и инструментального повторения, 5% языка. Половина естественно-языковых целей — полная программа; сохраняются отдельный разбор формулы, смысловые метки, исправление и трасса. Новых ответов большого учителя не добавлялось, чтобы сравнивать кодировку на общем материале.','',
      'Каждый вариант получил 8 000 обновлений с батчем128, то есть 1 024 000 выбранных примеров. Все четыре процесса обучались одновременно на двух полных B200. Контексты512/1024/2048 выбирались в соотношении80/10/10; микробатч128 поместился на всех длинах. Q4 применялся с первого обновления, активации обучения — BF16; проверка — фактические распакованные Q4-пакеты с FP32-арифметикой.','',
      f"Все восемь экспортов точно восстановлены из Q4 и повторно упакованы с совпадением полезной нагрузки. На CPU совпали {verify['cpu_b200_matches']}/{verify['compared']} последовательностей токенов с B200; FP16-хранение KV сохранило {verify['fp16_fp32_matches']}/{verify['compared']} последовательностей относительно FP32 CPU. Размеры реального кэша проверены, максимальный проверенный запрос — {verify['max_actual_prompt_tokens']} токенов.",'',
      '| Модель | Выход | Нативных генераций совпало | Токенов/с на хосте | Prefill512, с |','| --- | --- | ---: | ---: | ---: |']
    for arm in ARMS:
        for mode in MODES:
            x=native['models'][arm+'-'+mode];lines.append(f"| {labels[arm]} | {mode.upper()} | {x['greedy_generations_matched']}/{x['greedy_generations_total']} | {x['decode_tokens_per_second_median']:.1f} | {x['prefill512_seconds_median']:.3f} |")
    lines+=['',
      f"C++-декодер прошёл {native['portable_decoder_valid_roundtrips']} проверок обратимости и отверг {native['portable_decoder_invalid_inputs_rejected']} неверных входов. Нативный адаптер распознаёт только32 новых токена и передаёт остальной текст прежнему русскому BPE. Логиты сверены с HF; пакеты MKA собраны из тех же аудированных весов. Изменён исследовательский снимок ядра, исходники рабочего приложения другого агента не менялись.",'',
      'Это замеры нативного ядра на хосте, не PicoCalc/RP2350. Его фактический KV остаётся FP32; FP16 проверен отдельно как хранение кэша на Python-хосте. Полная интеграция адаптера с рабочим приложением и измерение памяти на устройстве здесь не проводились. Уменьшение числа токенов ответа само по себе не уменьшает заранее выделенный кэш на 2048 позиций.','',
      'Область опыта: стандартный МК-61, до105 байтов программы. Естественный язык проверяет семь арифметических операций на R0–R3, формальный набор дополнительно содержит управление и другие регистры. Расширенная память MK61S не использовалась. Короткая промежуточная формула не доказывает общего рассуждения или умения писать новые игры.','',
      'В составных проверках эталонные программы содержат до8 байтов, в формальном наборе — до16. На один ответ даётся до160 новых токенов. Это не испытание генерации полных105-байтных игр.','',
      f"[Все метрики]({root}/summary-local.json) · [Выбор снимков до теста]({root}/preselected.json) · [CPU и KV]({root}/local-verification.json) · [Нативная проверка]({root}/native/verification.json)",'']
    for arm in ARMS:
        lines.append(f"{labels[arm]}: [HEX Q4]({root}/export/endpoint/{arm}-hex/model.mkqb), [H32 Q4]({root}/export/endpoint/{arm}-h32/model.mkqb), [H32 MKA]({root}/native/{arm}-h32.mka).")
        lines.append(f"Лучшие по валидации: [HEX]({root}/export/best/{arm}-hex/model.mkqb), [H32]({root}/export/best/{arm}-h32/model.mkqb).")
    lines.append('');(here/'HUFFMAN_QAT_RESULTS.md').write_text('\n'.join(lines))
    final=here/'FINAL_RESULTS.md';marker='<!-- codec-qat-v1 -->';old=final.read_text().split(marker)[0].rstrip()
    final.write_text(old+'\n\n'+marker+'\n\n## Сравнение обучения HEX и Хаффмана-32\n\nЗавершены четыре одинаковых продолжения по8000 обновлений с батчем128. Основное сравнение использует фиксированные конечные снимки и140 новых условий. [Результаты и все веса](HUFFMAN_QAT_RESULTS.md).\n')
    state_path=here/'work-state.json';state=json.loads(state_path.read_text())
    state.setdefault('completed_training_runs_before_codec_qat',state['completed_training_runs'])
    state.setdefault('accounted_optimizer_updates_before_codec_qat',state['total_accounted_optimizer_updates_lower_bound'])
    state['completed_training_runs']=state['completed_training_runs_before_codec_qat']+4
    state['total_accounted_optimizer_updates_lower_bound']=state['accounted_optimizer_updates_before_codec_qat']+32000
    quality=any(all(r['summary'][part][kind]['rate']>=.9 for part in ['manual1','manual2','manual3']for kind in ['parse','program'])
      and min(r['summary'][part]['program']['rate']for part in ['context1024','context2048'])>=.8 and r['full_formal']['pass_rate']>=.95 for r in [*results.values(),*secondary.values()])
    state.update(phase='codec_qat_comparison_complete',training_and_evaluation_complete=True,all_own_remote_jobs_complete=True,
      remote_experiment_jobs_complete=True,free_language_coding_target_met=quality,final_report=str(here/'HUFFMAN_QAT_RESULTS.md'),
      final_export=str(root/'export'),next_action='Encoding comparison complete. Evaluate quality limits before further curriculum or architecture changes.')
    state['codec_qat_v1'].update(completed=True,primary_summary=compact,paired_comparisons=paired,quality_target_met=quality,
      all_four_sample_plans_matched=True,steps_completed_each=8000,final_exports=str(root/'export'),new_audit_opened=True)
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'primary':compact,'paired':paired,'quality_target_met':quality},ensure_ascii=False),flush=True)


if __name__=='__main__':
    # The collector itself uses stdlib Python; token-count measurement needs
    # the existing local transformers environment.
    try:import transformers
    except ImportError:
        import subprocess,sys
        interpreter=Path(__file__).resolve().parents[2]/'.build/squeal-chat-20261105/venv/bin/python'
        subprocess.run([str(interpreter),str(Path(__file__).resolve()),*sys.argv[1:]],check=True)
    else:main()
