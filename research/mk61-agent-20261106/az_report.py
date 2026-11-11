"""Compare continued branches and their own frozen parents on one fresh Q4 exam."""
import argparse
import collections
from pathlib import Path
import re
import statistics
from az_common import HERE,read,write,sha
from ay_report import paired
from ar_spec import infer,spec_text,expected,equivalent
from full_isa_vm import FullVM
from az_teacher import pool_for
from ha_protocol import assemble


def compact(report):
    result={k:v['summary']for k,v in report.items()if isinstance(v,dict)and'summary'in v}
    result['families']=report['primary']['families'];result['panels']=report['primary']['panels']
    result['sin22']=report['regression']['passed']
    for gate in ['raw','self']:
        records=report[gate]['records'];result[gate]=dict(result[gate])
        result[gate]['correct_DONE_public_ineligible']=sum(r['finished']and r['program_correct']and not r['eligible']for r in records)
        result[gate]['tool_or_compilation_errors']=sum(any(h['kind']=='error'for h in r['history'])for r in records)
        result[gate]['false_DONE_fraction_among_DONE']=result[gate]['false_DONE']/result[gate]['DONE']if result[gate]['DONE']else None
    return result


def fraction(v,key='passed'):return f'{v[key]}/{v["total"]}'


def main(root):
    assert read(root/'complete.json')['completed']and read(root/'postflight.json')['all_frozen_files_verified']
    assert read(root/'native-verification.json')['complete']
    choices=read(root/'preselected.json');assert not choices['closed_used_for_selection']
    reports={arm:read(root/arm/'closed.json')for arm in ['hex','spec']}
    parents={arm:read(root/('source-'+arm+'-closed.json'))for arm in reports}
    stats={'optimizer_updates':6000,'preselected':choices,'data':read(root/'teacher-frozen.json')['counts'],
        'trained':{a:compact(r)for a,r in reports.items()},'parent':{a:compact(r)for a,r in parents.items()},
        'paired':{'SPEC_minus_HEX':paired(reports['hex']['primary']['records'],reports['spec']['primary']['records']),
          **{a+'_continuation_minus_parent':paired(parents[a]['primary']['records'],reports[a]['primary']['records'])for a in reports}},
        'development_curves':{a:[{'step':step,'primary':r['primary']['summary'],'panels':r['primary']['panels'],
            'navigation':r['navigation']['summary'],'sin22':r['regression']['passed'],'raw':r['raw']['summary']}
            for step in [500,1500,3000]for r in [read(root/a/f'development-{step}.json')]]for a in reports}}
    goals={g['id']:g for line in(root/'closed-clean.jsonl').read_text().splitlines()for g in [__import__('json').loads(line)]}
    constant_goals=[g for g in goals.values()if g['family']=='constant']
    notation=re.compile(r'\b(?:sin|cos|tan|asin|acos|atan|arcsin|arccos|arctan|sqrt|square|abs|neg|reciprocal|exp|pow10|ln|log10|int|frac|sign|pow|tg|ctg|lg)\b',re.I)
    stats['wording_diagnostic']={}
    for label,wanted in [('explicit_function_notation',True),('without_explicit_function_names',False)]:
        ids={g['id']for g in goals.values()if bool(notation.search(g['task']))==wanted}
        stats['wording_diagnostic'][label]={'total':len(ids),**{stage:{a:sum(r['program_correct']for r in report['primary']['records']if r['id']in ids)
            for a,report in values.items()}for stage,values in [('parent',parents),('trained',reports)]}}
    stats['false_DONE_diagnostic']={}
    for a,report in reports.items():
        stats['false_DONE_diagnostic'][a]={}
        for gate in ['raw','self']:
            wrong=[r for r in report[gate]['records']if r['finished']and not r['program_correct']]
            stats['false_DONE_diagnostic'][a][gate]={'false_DONE':len(wrong),
                'initial_proposal_intent_correct':sum(bool(equivalent(r['declared_spec'],goals[r['task_id']]['spec'],goals[r['task_id']]['audit_inputs'])['tested_equal'])for r in wrong),
                'final_code_matches_own_spec':sum(r['spec_consistent']for r in wrong)}
    nontrivial=set()
    for g in constant_goals:
        x=expected(g['spec'],{})['X']
        if all(abs(x-v)>2e-6*max(1,abs(x),abs(v))for v in [0,1,-1]):nontrivial.add(g['id'])
    stats['constant_nontrivial_diagnostic']={'total':len(nontrivial),'excluded_near_zero_or_one':len(constant_goals)-len(nontrivial),
       **{stage:{a:sum(r['program_correct']for r in report['primary']['records']if r['id']in nontrivial)
                for a,report in values.items()}for stage,values in [('parent',parents),('trained',reports)]},
       'same_exam_no_additional_generations':True,'used_for_selection':False}
    shared={r['id']for r in reports['hex']['primary']['records']if r['program_correct']}&{r['id']for r in reports['spec']['primary']['records']if r['program_correct']}
    stats['same_successful_tasks_output_tokens']={'tasks':len(shared),**{a:statistics.mean(len(r['generation']['generated_token_ids'])for r in reports[a]['primary']['records']if r['id']in shared)if shared else None for a in reports}}
    if(root/'user-short-probes.json').exists():
        stats['user_short_probes']=[{'arm':r['arm'],'task':r['task'],'passed':r['passed'],
             'formula':r['result'].get('formula'),'actual':r['result'].get('actual')}for r in read(root/'user-short-probes.json')['records']]
    write(root/'comparison.json',stats)
    prepared=read(root/'prepared.json');policy=read(root/'policy.json');lessons=read(root/'lessons-frozen.json')
    lines=['# 3M Q4: константы, новые числа и полные циклы RUN', '',
      'Обе ветки продолжены от собственных ранее выбранных чекпойнтов: HEX и компактная SPEC. '
      'DeepSeek-V4.1-Flash создала русские формулировки и независимо перевела их обратно в формулы; обратный запрос не содержал исходного AST. '
      'Численная проверка отсеяла неверные переводы. Эталонный код и все положительные учебные DONE проверены настоящим ROM эмулятором. '
      'Учитель во время экзамена не вызывается.', '',
      f'После продолжения HEX решает {fraction(reports["hex"]["primary"]["summary"])}, '
      f'SPEC — {fraction(reports["spec"]["primary"]["summary"])}. '
      'Навигация RUN 00/01 стала надёжнее, однако проблема проверки смысла не решена: '
      f'в raw остаётся {reports["hex"]["raw"]["summary"]["false_DONE"]} ложных DONE у HEX '
      f'и {reports["spec"]["raw"]["summary"]["false_DONE"]} у SPEC. '
      'Отдельная перестановка таблицы констант выявила существенную хрупкость, особенно у HEX; '
      'высокую точность при обычном порядке таблицы нельзя переносить на произвольный порядок.', '',
      'Основная таблица показывает те же самые новые задания для сохранённых родителей и их продолжений. '
      'Одношаговая проверка принудительно выбирает WRITE; это отдельная способность от выбора следующего действия и от успешного завершения отладки.', '',
      '| Q4 | Одна попытка | Знакомые сочетания | Новая панель | Ошибки формата/компиляции |',
      '|---|---:|---:|---:|---:|']
    for label,report in [('HEX родитель',parents['hex']),('HEX продолжение',reports['hex']),('SPEC родитель',parents['spec']),('SPEC продолжение',reports['spec'])]:
        p=report['primary'];lines.append(f'| {label} | {fraction(p["summary"])} | {fraction(p["panels"]["known"])} | {fraction(p["panels"]["novel"])} | {p["summary"]["codec_errors"]} |')
    lines += ['', 'Отдельные семейства нового экзамена:', '',
      '| Семейство | HEX родитель | HEX продолжение | SPEC родитель | SPEC продолжение |', '|---|---:|---:|---:|---:|']
    for family in reports['hex']['primary']['families']:
        values=[r['primary']['families'][family]for r in [parents['hex'],reports['hex'],parents['spec'],reports['spec']]]
        lines.append('| '+family+' | '+' | '.join(fraction(v)for v in values)+' |')
    n=stats['constant_nontrivial_diagnostic']
    lines += ['',f'У {n["excluded_near_zero_or_one"]} константных задач ответ совпадает с 0 или ±1 в пределах допуска. '
        f'На оставшихся {n["total"]}: HEX {n["parent"]["hex"]} → {n["trained"]["hex"]}, '
        f'SPEC {n["parent"]["spec"]} → {n["trained"]["spec"]}. Это диагностический срез того же экзамена без новых генераций; '
        'он не использовался для выбора чекпойнта.']
    lines += ['', 'constant — вычисление только по числовым литералам; numeric — входные регистры и литералы; '
       'register — новые выражения с регистрами; composition — специально удержанные пары операций. '
       'Панель novel содержит новые числовые значения и удержанные композиции; это не только тест новых сочетаний.', '',
       '| Парная разность | п.п. | 95% bootstrap по задачам, п.п. | Только новое верно | Только исходное верно |',
       '|---|---:|---:|---:|---:|']
    for name,v in stats['paired'].items():
        lo,hi=v['paired_bootstrap_95'];lines.append(f'| {name} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} | {v["spec_only_correct"]} | {v["hex_only_correct"]} |')
    lines += ['', 'Интервалы отражают вариативность задач при одном запуске обучения. Между сидами повторов нет; '
       'небольшие различия без устойчивого интервала не считаются доказанным преимуществом.', '',
       '## Выбор RUN и завершение', '',
       'В навигационных пробах исходный код гарантированно правилен. Реальный WRITE оставляет проверенным только текущий случай. '
       'Модель должна выбрать недостающий RUN 00 либо RUN 01 и затем DONE; все действия свободные. '
       'На цикл отводится до пяти ответов. RUN не подставляется кодом оценки.', '',
       '| Q4 | Следующий RUN 00 | Следующий RUN 01 | Полный корректный цикл |', '|---|---:|---:|---:|']
    for label,report in [('HEX родитель',parents['hex']),('HEX продолжение',reports['hex']),('SPEC родитель',parents['spec']),('SPEC продолжение',reports['spec'])]:
        n=report['navigation']['summary'];lines.append(f'| {label} | {fraction(n["by_case"]["0"],"next_step_correct")} | {fraction(n["by_case"]["1"],"next_step_correct")} | {fraction(n,"cycle_pass")} |')
    lines += ['', 'Полная отладка: 128 новых условий × правильное/ошибочное начальное решение, до 12 действий. '
       'Успех требует правильного кода на отдельных аудиторских входах, допустимого DONE и обоих публичных запусков текущей редакции. '
       'Ложный DONE ниже означает завершение с неверным кодом. Верный код с DONE без необходимых запусков указан отдельно.', '',
       '| Q4 | Режим | Успешно | DONE | Ложных DONE | Верный код, непроверенный DONE | Исправлено ошибочных стартов |',
       '|---|---|---:|---:|---:|---:|---:|']
    for label,stage,arm in [('HEX родитель','parent','hex'),('HEX продолжение','trained','hex'),('SPEC родитель','parent','spec'),('SPEC продолжение','trained','spec')]:
        for gate in ['raw','self']:
            v=stats[stage][arm][gate];lines.append(f'| {label} | {gate} | {fraction(v)} | {v["DONE"]} | {v["false_DONE"]} | {v["correct_DONE_public_ineligible"]} | {v["wrong_starts_repaired"]}/{v["wrong_starts"]} |')
    lines += ['', 'raw оставляет решение о DONE модели. self проверяет код относительно её собственной одношаговой спецификации, '
       'поэтому ошибочное понимание условия может пройти такую проверку. Совпадение со своей формулой не доказывает верное понимание запроса. '
       'Низкое число ложных DONE нужно читать вместе с числом завершений и правильных решений.', '',
       'У SPEC абсолютное число ложных DONE выросло с 19 до 45, одновременно число всех DONE выросло с 35 до 254: '
       'доля ошибочных завершений снизилась с 54.3% до 17.7%. Это существенное улучшение покрытия, но не решение проблемы безопасности завершения. '
       'У HEX ложных DONE стало 48 вместо 78, доля снизилась с 43.1% до 19.2%.', '',
       'Примеры оставшихся ошибок в raw:']
    for a,report in reports.items():
        candidates=[r for r in report['raw']['records']if r['finished']and not r['program_correct']]
        candidates.sort(key=lambda r:bool(notation.search(goals[r['task_id']]['task'])))
        for row in candidates[:2]:
            g=goals[row['task_id']]
            try:actual=spec_text(infer(row['body'],g['pool'],g['spec']['angle']))
            except (ValueError,ArithmeticError):actual='символьный декодер не восстановил формулу'
            lines += ['',f'- **{a}:** {g["task"]}',f'  Требуется: `{spec_text(g["spec"])}`. Финальный код: `{actual}`. Сеть заявила DONE.']
    lines += ['',
       '## Данные, обучение и независимость', '',
       '| Набор | Деревьев | Условий |', '|---|---:|---:|']
    for name,d in stats['data'].items():lines.append(f'| {name} | {d["trees"]} | {d["questions"]} |')
    lines += ['', 'Часть русских условий учитель записал с явными именами функций, например sin(...) или frac(...). '
       'Эти примеры прошли проверку смысла, но нарушают желаемую форму полностью словесного русского условия. '
       'Это отдельное ограничение корпуса; его нельзя скрывать общей метрикой.', '',
       '| Формулировки того же экзамена | Всего | HEX родитель → продолжение | SPEC родитель → продолжение |',
       '|---|---:|---:|---:|']
    for label,v in stats['wording_diagnostic'].items():
        lines.append(f'| {label} | {v["total"]} | {v["parent"]["hex"]} → {v["trained"]["hex"]} | {v["parent"]["spec"]} → {v["trained"]["spec"]} |')
    lines += ['', 'В учебном наборе 1200 проверенных повторов только из прошлого train; прежние экзамены не повторяются. '
       'Новые сигнатуры не совпадают с прежними train/development/closed с учётом перестановок +/* и несущественного углового режима. '
       'Все алгебраические тождества этим не исключаются. Для development и closed удержаны отдельные числовые литералы; '
       'это отсутствие в AST и таблицах констант текущего и предыдущего курса, а не заявление об отсутствии чисел во всей истории сети.', '',
       f'Учебных состояний {lessons["rows"]:,}, допустимых по длине для обоих выходов {prepared["valid_lessons"]:,}; '
       f'RUN 00 / RUN 01: {lessons["RUN_counts"]["0"]:,} / {lessons["RUN_counts"]["1"]:,}. '
       'Есть первичное исправление, неудачная предыдущая правка, второе исправление и переход к другому текущему случаю. '
       'Счётчики бюджета и наблюдения получены настоящими Session, а не нарисованы в тексте.', '',
       'По 3000 обновлений на ветку, batch 32, Q4 на каждом прямом проходе, вычисления FP32. '
       'Каждый batch содержит по три RUN 00 и RUN 01; за обучение по 9000 каждого. '
       'Порядок выборок, бюджет и функция потерь одинаковы; контрольные digest совпадают. '
       'Продолжены существующие rank16 адаптеры и шесть строк действий, всего 318 208 обучаемых коэффициентов. '
       'Нового критика, DPO или штрафа за DONE нет. После слияния остаётся 3 022 080 параметров, контекст 1024. '
       'Русский входной словарь и тензоры вне адаптеров сохранены.', '',
       'Начальные файлы адаптеров совпадают с выбранными родителями. Перед первым обновлением на B200 '
       'проверено побайтовое совпадение исходных Q4 payload. При локальном восстановлении факторов на CPU '
       f'число отличающихся байтов составило {prepared["CPU_reconstruction_payload_byte_differences"]}; '
       'CPU-восстановление не использовалось как исходный родитель в экзамене или обучении.', '',
       'Чекпойнты 500/1500/3000 выбирались только на новом development. Ключ: сначала известная регрессия sin(22°), '
       'затем минимум качества знакомой/новой панели и навигации RUN 00/01, затем общая одношаговая точность и польза raw-отладки. '
       'Выбор каждого плеча зафиксирован до открытия closed; экзамен не использован для смены весов или порогов.', '',
       '| Ветка | Выбранный шаг |', '|---|---:|']
    for arm,choice in choices['choices'].items():lines.append(f'| {arm} | {choice["step"]} |')
    lines += ['', 'Последний шаг не принимается автоматически: все 3000 обновлений выполнены, '
       'но для экспорта используется заранее заданный ключ development. Подробные кривые, включая ложные DONE, '
       'сохранены в comparison.json. После выбора альтернативные чекпойнты на закрытом экзамене не сравнивались.']
    lines += ['', '## Известный синус 22° и таблица констант', '',
       'sin(22°) включён в обучение как известная регрессия. Его успех не считается новой экзаменационной задачей. '
       'Контрольный запрос: «Вычисли синус 22 градусов. Результат оставь в X; остановись.» Эталон ≈ 0.3746065934.', '',
       '| Q4 | Регрессия пройдена | Получено X в эмуляторе |', '|---|---:|---:|']
    vm=FullVM();text='Вычисли синус 22 градусов. Результат оставь в X; остановись.';pool=pool_for(text)
    for label,report in [('HEX родитель',parents['hex']),('HEX продолжение',reports['hex']),('SPEC родитель',parents['spec']),('SPEC продолжение',reports['spec'])]:
        reg=report['regression'];actual=None
        try:state,_=vm.execute(assemble(reg['program'],pool,'asm'),{},angle='DEG',max_commands=128,max_frames=1024);actual=state['numeric']['X']
        except (ValueError,ArithmeticError,RuntimeError):pass
        lines.append(f'| {label} | {reg["passed"]} | {actual} |')
    if 'user_short_probes'in stats:
        lines += ['', 'Дополнительные локальные запросы после экзамена проверяют минимальные формулировки и реальный az_chat.py. '
           'Это диагностические примеры, они не использованы для выбора или изменения весов и не добавлены к 479 экзаменационным задачам.', '',
           '| Ветка | Запрос | Верно | Фактическая формула |', '|---|---|---:|---|']
        for r in stats['user_short_probes']:lines.append(f'| {r["arm"]} | {r["task"]} | {r["passed"]} | {r["formula"]} |')
        lines += ['', 'У HEX успех полного контрольного запроса sin(22°) не переносится на короткое «Синус 22»: '
           'она выдаёт asin(22), что приводит к ошибке области определения. SPEC проходит оба варианта. '
           'Поэтому исправление известной регрессии нельзя объявлять полной устойчивостью к кратким формулировкам.']
    lines += ['', 'Дополнительная проверка перестановки новых констант и добавления отвлекающих чисел использует '
       'часть тех же AST; это проверка устойчивости, а не ещё один независимый тест.', '',
       '| Q4 | Устойчивость таблицы констант |', '|---|---:|']
    for label,report in [('HEX родитель',parents['hex']),('HEX продолжение',reports['hex']),('SPEC родитель',parents['spec']),('SPEC продолжение',reports['spec'])]:
        lines.append(f'| {label} | {fraction(report["pool_stress"]["summary"])} |')
    lines += ['', 'Перестановка затрагивает только дополнительные константы и добавляет отвлекающие значения; '
       'базовые 12 позиций сохраняются. Она не меняет математическое задание. '
       'Падение означает, что модель пока недостаточно надёжно связывает упомянутое число с произвольной позицией таблицы. '
       'Стабильный порядок pool_for является частью текущего протокола. На этом срезе веса и формат после экзамена не подбирались.']
    lines += ['', '## Экспорт и границы результата', '',
       'Оба слитых экспорта повторно проверены: сохранённый FP32 master → Q4 даёт те же байты. '
       'На выбранных потоках команд сравнивались B200, CPU и C++ decoder; веса и словарь проверены отдельно. '
       'Добавлены протокол таблицы литералов и пример локального запуска az_chat.py. Обе ветки сохранены независимо.', '',
       '| Ветка | MKA, байт | Native-проб | KV1024, байт | Workspace, байт |', '|---|---:|---:|---:|---:|']
    for arm,v in read(root/'native-verification.json')['models'].items():lines.append(f'| {arm} | {v["mka_bytes"]} | {v["probes"]} | {v["cache_bytes"]} | {v["workspace_bytes"]} |')
    lines += ['', 'Проверка численная, с конечным числом входов и допуском 2e-6; для некоторых константных выражений '
       'разные деревья могут давать одинаковый результат. Это не формальное доказательство для всех программ. '
       'Область курса — прямолинейная арифметика и необязательная запись результата; циклы и ветвления не обучались. '
       'Работа выполнялась на компьютере и сервере. Физические скорость и пиковая память PicoCalc не измерялись, '
       'прошивка и основной профиль не заменены. Свои учебные контейнеры завершены; прежние исходники и модели не изменены.', '',
       'Артефакты: '+str(root)+'. Метрики: comparison.json; подробные ответы: {hex,spec}/closed.json; '
       'новые условия: closed-clean.jsonl; модели: export/{hex,spec}/{hf,model.mkqb,model.mka}.', '']
    (HERE/'SEMANTIC_SPEC_CONSTANTS_RESULTS.md').write_text('\n'.join(lines))
    write(root/'report-receipt.json',{'report_sha256':sha(HERE/'SEMANTIC_SPEC_CONSTANTS_RESULTS.md'),'optimizer_updates':6000,'closed_used_for_selection':False})
    print(__import__('json').dumps(stats,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
