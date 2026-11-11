"""Report a self-predicted plan experiment, including the superseded setup."""
import argparse
import json
import shutil
from pathlib import Path
from an_common import HERE,PARENT,ARMS,read,write
from ak_report import brief,transitions


def load(root,name):return json.loads((root/name).read_text())


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);root=ap.parse_args().root.resolve()
    pre=load(root,'preselected.json');native=load(root,'native-verification.json');post=load(root,'postflight.json');data=load(root,'data-frozen.json');prepared=load(root,'prepared.json')
    assert native['complete']and not pre['fresh_used_for_selection']and not post['own_running_containers']
    initial=load(root,'initial-fresh.json');reports={'source':initial}
    for arm in ARMS:
        reports[arm]=load(root,arm+'/best-fresh.json');reports[arm+'-research']=load(root,arm+'/research-fresh.json')
    stats={n:brief(r)for n,r in reports.items()};selected=pre['selected_arm'];choice=pre['choices'][selected]
    retained=all(p['passed']>=initial[n]['passed']and p['false_DONE']<=initial[n]['false_DONE']and p['correct_controls_completed']>=initial[n]['correct_controls_completed']for n,p in reports[selected].items())
    improved=sum(p['false_DONE']for p in reports[selected].values())<sum(p['false_DONE']for p in initial.values())
    release=load(root.parent,'release-policy.json');assert release['created_before_new_exam_inspection']
    promoted=choice['step']>0 and retained and improved
    computed=data['superseded_original_optimizer_updates_lower_bound']+sum(load(root,a+'/training.json')['steps']for a in ARMS)
    lines=['# 3M Q4: понимание цели, чтение кода и собственный HEX-план','',
      f'Выбран по контролю: **{selected}, {choice["step"]} обновлений продолжения**, режим **{choice["runtime_mode"]}**. '
      f'Новые веса прошли условие выпуска на независимом экзамене: **{promoted}**. Экзамен не выбирает веса или режим.','',
      'В этом опыте разделены три учебные задачи: извлечь операцию и аргумент из русского условия; '
      'извлечь их из HEX без текста условия; распознать вид ошибки и исправить конкретные токены. '
      'Дополнительные головы операции, аргумента и типа ошибки используются при обучении и удаляются при экспорте. '
      'Самостоятельный план — полная программа-гипотеза в прежнем HEX+макросы.','',
      f'Данные: {data["goals"]} планирующих примеров, {data["code_reading"]} примеров чтения кода, '
      f'{data["tool_rows"]} шагов проверки/исправления, {data["retention"]} примеров удержания. '
      'Большая LLM не вызывалась: учитель использует авторские программы и ROM-верификацию.','',
      'Первоначальный вариант с сокращённым форматом состояния дал резкое падение контрольного успеха. '
      'Кроме того, два независимых первых этапа разошлись в весах. Прогон остановлен по контролю до просмотра '
      'экзамена, его исходники и результаты сохранены. Продолжение обеих веток начинается с одного фактического '
      'чекпойнта на шаге 250; оптимизаторы обеих веток сброшены. Привычный формат состояния восстановлен и '
      f'побитово сопоставлен с Session на {prepared["legacy_prompt_exact_examples"]} примерах.','',
      'Контроль и экзамен сохраняют исходные SHA замороженного первого варианта. Их формулировки не пересекаются '
      'с учебными. Проверяется перенос на новые формулировки и экземпляры знакомых семейств; совершенно новые '
      'алгоритмические семейства отдельно не удерживались.','',
      'У двух продолжающихся веток одинаковы стартовые веса и индексы учебных выборок. `direct` получает '
      'прежнее состояние. `planned` дополнительно получает собственную гипотезу сети и факты её исполнения '
      'на публичных входах. Гипотеза явно помечена как недостоверная. Эталон, скрытые тесты и ожидаемые значения '
      'в этот контекст не попадают; raw-DONE не блокируется внешним порогом.','',
      'Для обучения зафиксирована выборка из 1024 собственных планов, на середине продолжения они обновляются. '
      'На экзамене план строится заново текущей сетью для каждого уникального условия/набора констант. '
      'Если добавочный контекст слишком длинный, гипотеза целиком опускается; условие, код и реальные факты сохраняются. '
      'План требует отдельного вызова сети и запусков эмулятора, вне прежнего бюджета 10 действий проверяющего.','',
      f'Учёт вычислений: остановленный первый вариант — не менее {data["superseded_original_optimizer_updates_lower_bound"]} '
      f'обновлений; исправленное продолжение — по 500, суммарно **{computed}** новых SGD-обновлений. '
      'Общий этап в используемом чекпойнте — 250. Линейные диагностические пробы перед SGD подогнаны только '
      'по обучению замкнутым решением ridge-регрессии, без обновлений генератора.','',
      '| Новый экзамен Q4 | Решено /320 | Ложных DONE | Операции /192 | Ложных DONE | Завершение /96 | Ложных DONE |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for name,s in stats.items():
        m,k,c=[s[n]for n in ['main','skills','completion']]
        lines.append(f'| {name} | {m["passed"]} | {m["false_DONE"]} | {k["passed"]} | {k["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} |')
    lines+=['','Успех требует правильного кода, всех обязательных публичных исполнений и DONE. '
      'Правильный незавершённый код и UNSURE успехом не считаются.','',
      '| Основные эпизоды | Все DONE | Ошибок среди DONE | UNSURE | Правильный итоговый код |','|---|---:|---:|---:|---:|']
    for name,s in stats.items():
        p=s['main'];fraction=f'{p["wrong_fraction_of_DONE"]:.2%}'if p['all_DONE']else'—'
        lines.append(f'| {name} | {p["all_DONE"]} | {fraction} | {p["abstained"]} | {p["final_program_correct"]} |')
    meaning={'source':load(root,'initial-meaning-fresh.json')};planning={'source':load(root,'initial-planning-fresh.json')}
    for arm in ARMS:
        for role in ['best','research']:
            name=arm+('-research'if role=='research'else'');meaning[name]=load(root,arm+'/'+role+'-meaning-fresh.json');planning[name]=load(root,arm+'/'+role+'-planning-fresh.json')
    lines+=['','| Отдельная диагностика на новых условиях | Операция из цели | Аргумент из цели | Обе метки цели | Операция из кода | Аргумент из кода | Обе метки кода | План решает задачу |',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in ['source',*[a+'-research'for a in ARMS]]:
        values=[]
        for mode in ['goal','code']:
            r=meaning[name][mode];values += [f'{r[k]}/{r["total"]}'for k in ['operation','argument','both']]
        p=planning[name];values.append(f'{p["passed"]}/{p["total"]}');lines.append('| '+name+' | '+' | '.join(values)+' |')
    lines+=['','Операция/аргумент измеряются отдельными учебными классификаторами, а не свободным текстовым ответом. '
      'Исходные классификаторы обучены только на замороженных учебных признаках; их точность показывает '
      'восстанавливаемость информации линейной пробой. Финальные классификаторы обучаются вместе с адаптерами. '
      'Эти головы не присутствуют в исполняемой модели и не подсказывают проверяющему ответы. Полная корректность '
      'HEX-плана оценивается ROM только офлайн. Типы выражений диагностической головы не ограничивают '
      'доступный стандартный набор команд МК-61.','',
      '| Использование собственной гипотезы | Гипотеза верна / эпизодов | Успех при неверной гипотезе | Ложный DONE при неверной гипотезе |',
      '|---|---:|---:|---:|']
    hypothesis={}
    for name in ['planned','planned-research']:
        rows=[r for p in reports[name].values()for r in p['details']if'planning'in r]
        if not rows:continue
        bad=[r for r in rows if not r['planning']['program_correct_offline_only']]
        v={'episodes':len(rows),'correct_hypotheses':len(rows)-len(bad),'bad_hypotheses':len(bad),
          'success_with_bad_hypothesis':sum(r['pass']for r in bad),'false_DONE_with_bad_hypothesis':sum(r['finished']and not r['program_correct']for r in bad)}
        hypothesis[name]=v;lines.append(f'| {name} | {v["correct_hypotheses"]}/{len(rows)} | {v["success_with_bad_hypothesis"]}/{len(bad)} | {v["false_DONE_with_bad_hypothesis"]}/{len(bad)} |')
    lines+=['','| planned-research: исходный код / гипотеза | Эпизодов | Решено | Ложных DONE |','|---|---:|---:|---:|']
    rows=[r for p in reports['planned-research'].values()for r in p['details']if'planning'in r]
    for initial_ok in [True,False]:
        for plan_ok in [True,False]:
            subset=[r for r in rows if bool(r['initially_correct'])==initial_ok and bool(r['planning']['program_correct_offline_only'])==plan_ok]
            lines.append('| '+('верный'if initial_ok else'неверный')+' / '+('верна'if plan_ok else'неверна')+
                f' | {len(subset)} | {sum(r["pass"]for r in subset)} | {sum(r["finished"]and not r["program_correct"]for r in subset)} |')
    visibility={'episodes':len(rows),'any_visible_valid_plan':0,'first_visible_valid_plan':0,
      'false_DONE_with_correct_hypothesis':0,'false_DONE_with_correct_hypothesis_visible':0,
      'false_DONE_with_correct_hypothesis_visible_X_mismatch':0}
    for r in rows:
        hs=[h for h in r['history']if'prompt'in h and'generation'in h]
        visibility['any_visible_valid_plan']+=any('Гипотеза модели HEX:'in h['prompt']for h in hs)
        visibility['first_visible_valid_plan']+=bool(hs and'Гипотеза модели HEX:'in hs[0]['prompt'])
        if r['finished']and not r['program_correct']and r['planning']['program_correct_offline_only']:
            visibility['false_DONE_with_correct_hypothesis']+=1
            h=next(h for h in reversed(hs)if h['generation'].get('action')=='done');visible='Гипотеза модели HEX:'in h['prompt']
            visibility['false_DONE_with_correct_hypothesis_visible']+=visible
            visibility['false_DONE_with_correct_hypothesis_visible_X_mismatch']+=visible and'X совпал с текущим: нет'in h['prompt']
    write(root/'hypothesis-visibility.json',visibility)
    lines+=['',f'Валидная гипотеза была видна хотя бы на одном шаге в {visibility["any_visible_valid_plan"]}/{len(rows)} эпизодов; '
      f'на первом шаге — в {visibility["first_visible_valid_plan"]}/{len(rows)}. '
      f'В {visibility["false_DONE_with_correct_hypothesis_visible_X_mismatch"]} ложных DONE гипотеза была правильной '
      '(по офлайн-оценке), присутствовала в последнем запросе и сопровождалась явным несовпадением X. '
      'Следовательно, низкая точность построения плана объясняет лишь часть провала этого режима.']
    lines+=['','Отбор требует на каждой контрольной панели не меньше успехов и завершённых правильных стартов, '
      'не больше ложных DONE, чем у исходного legacy-профиля. Затем сравнивается '
      '(успех − 4×ложные DONE)/размер с весами 0.60/0.25/0.15. Исходные веса включены как шаг 0. '
      'Профили research показывают лучшую контрольную полезность среди новых весов и могут нарушать удержание. '
      'Выпуск дополнительно требует удержания экзамена и снижения суммарных ложных DONE; экзамен не выбирает другой чекпойнт.','',
      '| Контроль | Шаг продолжения | Решено /160 | Ложных DONE | Операции /96 | Ложных DONE | Завершение /48 | Ложных DONE | Удержание |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    base=load(root,'initial-development.json')
    for arm in ['source',*ARMS]:
        for step in ([0]if arm=='source'else[250,500]):
            r=base if arm=='source'else load(root,f'{arm}/development-{step}.json')
            keep=all(p['passed']>=base[n]['passed']and p['false_DONE']<=base[n]['false_DONE']and p['correct_controls_completed']>=base[n]['correct_controls_completed']for n,p in r.items())
            m,k,c=[r[n]for n in ['main','skills','completion']];lines.append(f'| {arm} | {step} | {m["passed"]} | {m["false_DONE"]} | {k["passed"]} | {k["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} | {keep} |')
    shutil.copytree(root/'export'/selected if promoted else PARENT/'export/lr10-terminal',root/'export/recommended',dirs_exist_ok=True)
    lines+=['',('Новые веса приняты как исследовательская рекомендация.'if promoted else'**Новые веса не приняты.** `recommended` сохраняет исходные веса и прежний режим.'),'','Ошибки и регрессии:','']
    paired={}
    for name in [selected,*[a+'-research'for a in ARMS]]:
        paired[name]={n:transitions(initial[n],p)for n,p in reports[name].items()};wrong=[];lost=[]
        for panel,p in reports[name].items():
            for b,r in zip(initial[panel]['details'],p['details']):
                if r['finished']and not r['program_correct']:wrong.append({'panel':panel,'episode':r,'baseline':b})
                if b['pass']and not r['pass']:lost.append({'panel':panel,'episode':r,'baseline':b})
        for suffix,rows in [('false-DONE',wrong),('lost-success',lost)]:
            p=root/f'{name}-{suffix}.jsonl';p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows));lines.append(f'- {name}: {suffix}, {len(rows)} — [{p.name}]({p}).')
    error_types=root/'error-type-diagnostics.json'
    error_diagnostics=load(root,error_types.name)if error_types.exists()else None
    if error_diagnostics:
        lines+=['','| Учебный диагноз | Верный тип ошибки на первых состояниях | Ложные DONE, где диагноз сигналил ошибку | Правильные DONE, где диагноз ошибочно сигналил ошибку |',
          '|---|---:|---:|---:|']
        for arm,d in error_diagnostics.items():
            first=d['first_skill_states'];at=d['at_actual_DONE']
            lines.append(f'| {arm} | {first["correct"]}/{first["total"]} | {at["wrong_flagged_as_error"]}/{at["wrong_total"]} | {at["correct_flagged_as_error"]}/{at["correct_total"]} |')
        lines+=['','Диагноз вычислен после обучения и не управляет raw-решением DONE. '
          f'Полные матрицы пяти классов: [error-type-diagnostics.json]({error_types}).']
    compiler=root.parent/'compiler-development-diagnostic.json'
    if compiler.exists():
        cp=load(root.parent,compiler.name);lines+=['',f'Дополнительная контрольная диагностика ранее замороженного профиля compiler: '
            f'{cp["passed"]}/{cp["total"]} самостоятельных решений на 24 контрольных операционных задачах. '
            'Использован прежний формат запроса компилятора; этот профиль не подсказывал планы текущим веткам и не участвовал в отборе.']
    lines+=['','Экспорт и исполнение:','']
    for name,p in native['models'].items():
        if name=='compiler':continue
        lines.append(f'- {name}: Q4 CPU/B200 {p["cpu_matches"]}/{p["probes"]}, C++/B200 {p["native_matches"]}/{p["probes"]}; '
          f'проб построения плана {len(p.get("planning_probes",[]))}; MKA {p["package_bytes"]:,} байт. '
          'Входной словарь и неадаптируемые тензоры побитово сохранены.')
    p=native['models'][selected];lines += [f'- Исполняемая модель — 3 022 080 параметров. KV {p["cache_bytes"]:,} байт при 1024 токенах; '
      'учебные классификаторы удалены. Сохраняются гипотеза и её публичные результаты; режим planned требует дополнительного вызова сети.',
      '- Исходники, данные, исходный и общий чекпойнты проверены по SHA; все собственные GPU-задания завершены.',
      '- Физический PicoCalc не измерялся, прошивка не менялась.']
    lines+=['','Артефакты для воспроизведения:','',
      f'- Ветка без плана: [Q4 MKA]({root/"export/direct-research/model.mka"}), [HF]({root/"export/direct-research/hf"}).',
      f'- Ветка с собственным планом: [Q4 MKA]({root/"export/planned-research/model.mka"}); её режим воспроизводится через [an_eval.py]({HERE/"an_eval.py"}).',
      f'- Обычный локальный runner для ветки без плана: [aj_chat.py]({HERE/"aj_chat.py"}), `--root {root} --arm direct-research --native`.',
      'Два варианта обучены по одному разу; небольшой суммарный прирост ветки без плана требует повторной проверки на других выборках.']
    path=HERE/'HEX_HYPOTHESIS_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    summary={'completed':True,'selected_arm':selected,'selected_step':choice['step'],'runtime_mode':choice['runtime_mode'],'new_checkpoint_promoted':promoted,
      'optimizer_updates':computed,'continuation_updates':1000,'superseded_updates':data['superseded_original_optimizer_updates_lower_bound'],
      'new_exam':stats,'meaning':meaning,'planning':{n:{k:p[k]for k in ['total','passed']}for n,p in planning.items()},
      'hypothesis_effect':hypothesis,'paired_transitions':paired,'native_verified':True,'fresh_used_for_selection':False,'physical_device_measured':False}
    summary['error_type_diagnostics']=error_diagnostics
    summary['hypothesis_visibility']=visibility
    write(root/'summary.json',summary);state=load(HERE,'work-state.json')
    if not state.get('hex_hypothesis_v2',{}).get('completed'):
        state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=computed
        state['superseded_training_runs']=state.get('superseded_training_runs',0)+2
    state.update(phase='hex_hypothesis_v2_complete',active_experiment=None,all_own_jobs_complete=True,latest_report=str(path),
      next_action='Review split diagnostics, own HEX hypothesis ablation, and newly graded Q4 errors; no firmware deployment requested.')
    state['hex_hypothesis_v2']={'completed':True,'root':str(root),'report':str(path),'summary':summary};write(HERE/'work-state.json',state)
    print(json.dumps({'completed':True,'report':str(path),'selected':selected,'step':choice['step'],'promoted':promoted}),flush=True)


if __name__=='__main__':main()
