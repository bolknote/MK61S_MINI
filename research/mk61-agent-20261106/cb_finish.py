"""Summarize completed actor adaptation, separate protocol effects, and account SGD once."""
import json
import time
from cb_common import ROOT,HERE,read,write,rows,sha,check_frozen
from by_finish import analyze,transitions
from bl_spec import install
from bl_vm import CachedVM


def brief(value):return {k:value[k]for k in ['total','passed','correct_starts_completed','wrong_starts_repaired','false_DONE','correct_starts_corrupted','context_overflows','abstained']}


def main():
    check_frozen();install();vm=CachedVM();root=ROOT/'server-results'
    assert read(root/'controller-complete.json')['all_own_workers_joined']and read(root/'postflight.json')['Qwen_health']=='200'
    native=read(root/'native-verification.json');assert native['complete']
    training=read(root/'training.json');selection=read(root/'preselected.json');assert not selection['closed_seen']
    roles=read(root/'analysis-audit-roles.json'if(root/'analysis-audit-roles.json').exists()else root/'audit-roles.json');closed={};reports={};goals=rows(ROOT/'closed.jsonl')
    for role,formats in roles['evaluated'].items():
        for format in formats:
            name=role+'_'+format;reports[name]=read(root/f'closed-{role}-{format}.json');closed[name]=analyze(reports[name],goals,vm)
    selected='selected_notes'if roles['selected_step']else'parent_notes'
    final='final_notes'if'final'in roles['evaluated']else selected
    recommended='selected_notes'if roles['selected_step']else'parent_original'
    pairs={'visible_review_state_and_guidance':('parent_original','parent_full'),'shortening_with_counter':('parent_full','parent_notes'),
           'selected_weights_at_same_format':('parent_notes',selected),'final_weights_at_same_format':('parent_notes',final),
           'selected_vs_legacy_reference':('parent_original',recommended)}
    trained_original=final.rsplit('_',1)[0]+'_original'
    if trained_original in reports:pairs['trained_weights_in_legacy_format']=('parent_original',trained_original)
    comparisons={name:transitions(reports[a],reports[b],goals)for name,(a,b)in pairs.items()}
    development={};selection_diagnostics={}
    for role in ['parent',*[f'step-{s}'for s in read(ROOT/'policy.json')['checkpoints']]]:
        development[role]={}
        for format in ['original','full','notes']:
            development[role][format]={split:read(root/f'{role}-{split}-{format}.json')['own']['summary']for split in ['development','retention']}
    for step in read(ROOT/'policy.json')['checkpoints']:
        role=f'step-{step}';decision=read(root/f'selection-{step}.json');retention={}
        for format in ['original','full','notes']:
            old={r['id']:r for r in read(root/f'parent-retention-{format}.json')['own']['records']}
            new={r['id']:r for r in read(root/f'{role}-retention-{format}.json')['own']['records']}
            retention[format]={'lost_successes':[k for k in old if old[k]['pass']and not new[k]['pass']],
                'new_successes':[k for k in old if not old[k]['pass']and new[k]['pass']]}
        selection_diagnostics[role]={'eligible':decision['eligible'],
            'failed_checks':[k for k,v in decision['checks'].items()if not v],'retention':retention}
    result={'complete':True,'optimizer_updates':training['optimizer_updates'],'selected_step':roles['selected_step'],
        'closed_tasks':len(goals),'fresh_composition_families':32,'closed_used_for_selection':False,
        'translator_unchanged':True,'selected_alias':selected,'recommended_runtime_alias':recommended,
        'product_profile_modified':False,'final_alias':final,'closed':closed,'comparisons':comparisons,
        'frozen_translator_primary':reports['parent_original']['primary']['summary'],
        'development':development,'selection':selection,'selection_diagnostics':selection_diagnostics,'native_streams':native['streams_verified'],
        'development_loss_examples':read(ROOT/'development-losses.json')if(ROOT/'development-losses.json').exists()else None,
        'supplementary_protocol':read(ROOT/'extra-protocol.json')if(ROOT/'extra-protocol.json').exists()else None}
    write(ROOT/'comparison.json',result)
    report=HERE/'PAIRED_ACTOR_FORMAT_TRAINING_RESULTS.md';a=closed['parent_notes']['summary'];b=closed[final]['summary']
    lines=['# Дообучение исполнителя на двух форматах','',
        f"Завершены {training['optimizer_updates']} обновлений свежего адаптера исполнителя 3M. На новых 256 задачах в Q4 при одинаковом коротком формате завершения {a['passed']}→{b['passed']} из 512, исправления {a['wrong_starts_repaired']}→{b['wrong_starts_repaired']} из 256, принятые ложные DONE {a['false_DONE']}→{b['false_DONE']}, итоговая порча {a['correct_starts_corrupted']}→{b['correct_starts_corrupted']}. По контрольным циклам до финального теста выбран шаг {roles['selected_step']} (0 — исходный исполнитель). Рабочий профиль не заменён.",'',
        'Переводчик BU1500 и механическая проверка заморожены. Обучались 317 440 параметров rank16/alpha32 в Q/V attention и MLP, все остальные тензоры, включая словарь и строки действий, сохранены. После слияния остаются прежние 3 022 080 параметров; Q4 применялся на каждом обучающем проходе. Не использовались DPO, штраф за DONE или нейросетевой критик.','',
        '## Протокол и разметка','',
        'В исходном обычном запросе не было явного признака уже использованного пересмотра SPEC. Для обучения с разными правильными действиями DIAG/UNSURE этот признак нужен в видимом состоянии. В оба сравниваемых формата одинаково добавлен реальный счётчик «Разборов SPEC осталось: 0/1» и сообщение об исчерпанном пересмотре. Прежний режим без счётчика также измерен отдельным контролем. Полномочия модели, число пересмотров, проверка DONE, RUN, откат и бюджет 12 действий не менялись. Это раскрытие существующего состояния, без доступа к эталону.','',
        'full сохраняет прежнюю справку; notes сокращает только общие правила на 68 токенов при том же счётчике. Справка вызовов и DIAG сохранена. Учебные пары имеют одну задачу, состояние и проверенную цель; успешный старый опыт также повторяется в прежнем формате без счётчика. Для слишком длинных состояний использован только помещающийся notes, явно продублированный для фиксированного микробатча. Все переменные публичные поля сохранены; скрытый эталон есть только у разметчика и независимого измерителя.','',
        'Курс: 18 005 уникальных состояний. Использованы 352 прежние задачи и 64 новых AST с 127 формулировками — всего 479 вариантов условий. Добавлены полные проверенные циклы и 6338 состояний из реальных прошлых траекторий до отбора по длине и дедупликации. Цели включают правильный WRITE, оба RUN, DONE, DIAG 04 при неверной SPEC и UNSURE после неудачного использованного пересмотра или недостаточного бюджета. Есть положительные примеры после использованного пересмотра. Противоречивых меток для одинаковых запросов нет. 32 старые успешные задачи отложены для сохранения поведения.','',
        'Смесь на шаг: три пары правильного/неправильного кода, четыре повтора успешного поведения, два RUN, два DIAG, один UNSURE, один пример после отклонённого DONE; каждое состояние представлено двумя форматами. Loss: action CE +2 body CE +0.05 согласование распределений действий +0.2 KD только верных предсказаний исходной модели на успешном повторе. Микробатч4, накопление8, итог32 последовательности, AdamW LR1e-5 с разминкой и косинусом, clipping1.','',
        '## Выбор до финального теста','',
        'Проверки после 300 и 1200 обновлений: новые 64 задачи и 32 отложенные старые успешные задачи в original/full/notes. Требуется минимум +2 завершения notes на development, сохранение завершений, исправлений и доведённых правильных стартов во всех форматах/панелях, не больше ложных принятых DONE и итоговой порчи, ни одного потерянного успеха на retention. При провале сохраняется исходная модель; последний обученный вариант всё равно проходит исследовательский аудит. Шаг 0 означает исходные веса и прежний входной формат original. Сравнения selected_weights_at_same_format измеряют только выбранные веса в контрольном notes, а selected_vs_legacy_reference — весь рекомендованный режим.','',
        '| Шаг | Формат | Панель | Завершено | Исправлено | Верный старт доведён | Принятые ложные DONE | Порча |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    if trained_original in closed:
        x=closed['parent_original']['summary'];y=closed[trained_original]['summary']
        lines[4:4]=[f"В прежнем формате original обученные веса дали {x['passed']}→{y['passed']} завершений, {x['wrong_starts_repaired']}→{y['wrong_starts_repaired']} исправлений, но принятые ложные DONE выросли {x['false_DONE']}→{y['false_DONE']}, итоговая порча {x['correct_starts_corrupted']}→{y['correct_starts_corrupted']}. Рост числа решённых эпизодов сопровождается регрессией безопасности; дополнительный аудит не используется для смены заранее выбранного чекпойнта.",'']
    for role,formats in development.items():
        for format,panels in formats.items():
            for split,s in panels.items():lines.append(f"| {role} | {format} | {split} | {s['passed']}/{s['total']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['false_DONE']} | {s['correct_starts_corrupted']} |")
    lines+=['','| Шаг | Формат | Потеряно прежних успехов retention | Новых успехов retention |',
        '|---|---|---:|---:|']
    for role,entry in selection_diagnostics.items():
        for format,t in entry['retention'].items():lines.append(f"| {role} | {format} | {len(t['lost_successes'])} | {len(t['new_successes'])} |")
    lines+=['','Критерий проверяет сохранение отдельных успешных эпизодов, поэтому рост общего числа завершений на retention сам по себе не делает чекпойнт допустимым. Точные идентификаторы потерь и проваленные проверки сохранены в `comparison.json` → `selection_diagnostics`.','']
    if result['development_loss_examples']:
        examples=[v for panel in result['development_loss_examples'].values()for v in panel['lost']]
        replaced=sum(v['old_first_action']=='diag'and v['new_first_action']in ['write','done']and v['replans']==0 for v in examples)
        lines+=[f"В отдельном разборе {len(examples)} потерянных эпизодов retention у финальных весов в {replaced} случаях исходный первый DIAG заменён WRITE/DONE и пересмотра SPEC не было. Наблюдались повторные WRITE/RUN, отказ и переполнение; это описание траекторий, а не установленная причинность отдельных коэффициентов.",'']
    lines+=['','## Новый финальный набор, Q4','',
        '256 новых AST, включая 160 задач из 32 новых семейств композиций, по 32 унарных, бинарных и чисто константных. Новые литералы и сочетания операций исключены из обучения и видимых учебных состояний. Все финальные AST сохранены; DeepSeek дал обычные русские условия, две слепые обратные проверки восстановили их смысл, компилятор и эмулятор подтвердили численные программы. Это проверки тем же учителем, а не независимые человеческие метки. Ни одна генерация студента на финальном наборе не использовалась для выбора чекпойнта.','',
        '| Версия | Формат | Завершено | Исправлено /256 | Верный старт доведён /256 | Принятые ложные DONE | Итоговая порча | Переполнение | Отказ |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,entry in closed.items():
        s=entry['summary'];lines.append(f"| {name} | {name.rsplit('_',1)[1]} | {s['passed']}/512 | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['false_DONE']} | {s['correct_starts_corrupted']} | {s['context_overflows']} | {s['abstained']} |")
    if(ROOT/'extra-protocol.json').exists():
        lines+=['','Дополнительный исследовательский аудит обученных весов в прежнем формате original зафиксирован отдельно после чтения development, до получения завершённых финальных отчётов, когда финальный прогон уже начался. Он не меняет критерий выбора и не используется для повторного выбора чекпойнта. Его результаты позволяют отделить обучение от нового видимого счётчика пересмотров.','']
    lines+=['','Сравнение parent_original→parent_full измеряет видимый счётчик вместе с условной справкой DIAG при уже использованном пересмотре; parent_full→parent_notes — сокращение правил; parent_notes→обученная версия notes — обновление весов при одинаковом протоколе. Первоначальные переводы SPEC и их токены во всех вариантах совпадают: переводчик не дообучался. Все режимы финального теста используют собственную SPEC; эталон агенту не подставлялся.','',
        '| Версия | Неверный WRITE при верном старте | Неверный кандидат перед откатом | Ложных заявлений DONE / всех | Пересмотров |',
        '|---|---:|---:|---:|---:|']
    for name,entry in closed.items():
        s=entry['summary'];c=entry['counts'];lines.append(f"| {name} | {c.get('correct_start:with_wrong_WRITE',0)} | {c.get('correct_start:wrong_candidate_at_exit',0)} | {s['false_DONE_claims']}/{s['all_DONE_claims']} | {s['replans']} |")
    lines+=['','Итоговая порча считается после механического отката. Ложное заявление DONE может быть отклонено упряжью; оно отличается от принятого ложного DONE. Проверка DONE сравнивает код с заявленной SPEC, поэтому ошибочный разбор русского условия всё ещё может пройти проверку.','',
        '## Парная неопределённость','',
        '95% интервалы: 10 000 парных bootstrap-выборок по 256 задачам, оба старта остаются вместе. Один прогон обучения; измерение не доказывает предел ёмкости и не охватывает произвольные ветвления/циклы МК-61.','',
        '| Сравнение | Завершения, п.п. [95%] | Исправления, п.п. [95%] | Принятые ложные DONE, п.п. [95%] |',
        '|---|---:|---:|---:|']
    primary=result['frozen_translator_primary'];at=lines.index('## Парная неопределённость')-1
    lines[at:at]=['',f"Замороженный переводчик верно разобрал {primary['intent_correct']}/{primary['total']} новых условий с первой попытки. Ошибки этого этапа могут быть исправлены только штатным повторным разбором; качество генерации кода и качество понимания условия оцениваются раздельно."]
    for name,entry in comparisons.items():
        cells=[]
        for key in ['completion','repairs','accepted_false_DONE']:
            q=entry['paired_uncertainty'][key];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.2f} [{lo:+.2f}; {hi:+.2f}]")
        lines.append('| '+name+' | '+' | '.join(cells)+' |')
    lines+=['','## Экспорт и выполнение','',
        f"Сохранённые мастера воспроизвели Q4 payload; во всех {native['streams_verified']} выбранных генерациях токены совпали на B200/CPU/C++. Неизменные словарь, строки действий и переводчик проверены. Один буфер весов {native['one_weight_buffer_bytes']} байт, host-KV {native['KV_bytes']} байт, workspace {native['workspace_bytes']} байт; физический PicoCalc не измерялся.",'',
        f"Пик зарезервированной GPU-памяти обучения: {training['peak_reserved_MiB']:.1f} МиБ. Все собственные задачи завершены, Qwen отвечает 200. Исходный продуктовый профиль не заменён.",'',
        'Артефакты: `.build/mk61-agent-20261106/spec-actor-paired-formats-v1`; `comparison.json`, `server-results/training.json`, `server-results/preselected.json`, `server-results/native-verification.json`.','']
    report.write_text('\n'.join(lines))
    state_path=HERE/'work-state.json';state=read(state_path);entry=state.get('latest_paired_actor_training',{})
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=1;state['total_accounted_optimizer_updates_lower_bound']+=training['optimizer_updates']
    entry.update(phase='complete',complete=True,optimizer_updates=training['optimizer_updates'],ledger_accounted=True,
        selected_step=roles['selected_step'],report=str(report),native_streams=native['streams_verified'],closed={k:brief(v['summary'])for k,v in closed.items()})
    state.update(latest_paired_actor_training=entry,active_experiment=None,all_own_jobs_complete=True,phase='paired_actor_training_complete',
        next_action='Interpret actor-weight gains separately from visible-review-counter and prompt changes; retain the preselected checkpoint and require real repair/safety preservation before product use.')
    write(state_path,state);write(ROOT/'finish.json',{'complete':True,'optimizer_updates':training['optimizer_updates'],'ledger_accounted':True,
        'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print(json.dumps({'report':str(report),'selected_step':roles['selected_step'],'updates':training['optimizer_updates'],
        'closed':entry['closed'],'native_streams':native['streams_verified'],'completed_training_runs':state['completed_training_runs'],
        'total_accounted_optimizer_updates_lower_bound':state['total_accounted_optimizer_updates_lower_bound']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
