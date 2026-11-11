"""Report fresh self-check results and separately the nineteen retired episodes."""
import argparse
import json
import re
from pathlib import Path
from bc_common import ROOT,HERE,read,write,sha
from ba_report import summary,cluster_difference,frac

def main(root):
    assert read(root/'complete.json')['completed']and read(root/'native-verification.json')['complete']
    assert read(root/'postflight.json')['all_frozen_files_verified']
    selection=read(root/'preselected.json');assert not selection['closed_used_for_selection']
    reports={name:read(root/name/'closed.json')for name in ['parent','spec']};old,new=reports['parent'],reports['spec']
    stats={'optimizer_updates':8000,'selected':selection,'analysis':read(ROOT/'analysis.json'),
        'data':read(root/'teacher-frozen.json')['counts'],'parent':summary(old),'spec':summary(new),
        'retired19':{name:read(root/name/'retired19-regression.json')for name in reports},
        'paired':{'primary':cluster_difference(old['primary']['records'],new['primary']['records'],lambda r:r['program_correct']),
          'self_success':cluster_difference(old['self']['records'],new['self']['records'],lambda r:r['pass'],'task_id'),
          'self_false_DONE':cluster_difference(old['self']['records'],new['self']['records'],lambda r:r['finished']and not r['program_correct'],'task_id')},
        'development_curves':{run:[{'step':step,'summary':summary(read(root/run/f'development-{step}.json'))}for step in [1000,2500,4000]]for run in ['seed-a','seed-b']}}
    for name,r in reports.items():
        intent={x['id']:x['intent']['tested_equal']for x in r['primary']['records']}
        records=r['self']['records'];bad=[x for x in records if x['finished']and not x['program_correct']]
        stats[name]['self_diagnosis']={'wrong_initial_hypothesis_false_DONE':sum(not intent[x['task_id']]for x in bad),
           'final_code_matches_own_wrong_hypothesis':sum(x['spec_consistent']for x in bad),
           'correct_final_code_UNSURE':sum(x['abstained']and x['program_correct']for x in records),
           'correct_starts_corrupted':sum(x['initially_correct']and not x['program_correct']for x in records)}
    if(root/'recovery-policy.json').exists():
        stats['development_adapter_strength_recovery']={'policy':read(root/'recovery-policy.json'),
            'runs':{name:read(root/name/'recovery-complete.json')for name in ['seed-a','seed-b']}}
    if(root/'safety/closed.json').exists():
        specialist=read(root/'safety/closed.json')
        stats['supplementary_self_profile']={'policy':read(root/'specialist-policy.json'),
            'summary':summary(specialist),'retired19':read(root/'safety/retired19-regression.json'),
            'paired':{'primary':cluster_difference(old['primary']['records'],specialist['primary']['records'],lambda r:r['program_correct']),
                'self_success':cluster_difference(old['self']['records'],specialist['self']['records'],lambda r:r['pass'],'task_id'),
                'self_false_DONE':cluster_difference(old['self']['records'],specialist['self']['records'],lambda r:r['finished']and not r['program_correct'],'task_id')}}
    stats['closed_self_false_DONE_reduced']=stats['spec']['self']['false_DONE']<stats['parent']['self']['false_DONE']
    old_states={(x['task_id'],x['initially_correct']):x for x in old['self']['records']}
    new_states={(x['task_id'],x['initially_correct']):x for x in new['self']['records']};assert old_states.keys()==new_states.keys()
    bad=lambda x:x['finished']and not x['program_correct']
    stats['self_paired_transitions']={'old_false_DONE_removed':sum(bad(old_states[k])and not bad(new_states[k])for k in old_states),
        'new_false_DONE_introduced':sum(not bad(old_states[k])and bad(new_states[k])for k in old_states),
        'new_successes':sum(not old_states[k]['pass']and new_states[k]['pass']for k in old_states),
        'lost_successes':sum(old_states[k]['pass']and not new_states[k]['pass']for k in old_states)}
    if(root/'user-probes.json').exists():stats['user_probes']=read(root/'user-probes.json')
    write(root/'comparison.json',stats)
    b,n=stats['parent']['self'],stats['spec']['self'];chosen=selection['selected'];analysis=stats['analysis'];l=read(root/'lessons-frozen.json');prep=read(root/'prepared.json')
    lines=['# SPEC Q4: обучение на19 ложных DONE самопроверки','',
       f'На новом закрытом наборе ложных DONE в режиме self: **{b["false_DONE"]} → {n["false_DONE"]}** из {n["total"]} эпизодов. '
       f'Правильных принятых завершений: **{b["passed"]} → {n["passed"]}**. '
       f'Обычная точность программ: {frac(stats["parent"]["primary"])} → {frac(stats["spec"]["primary"])}. '
       'Все числа до/после относятся к одному новому экзамену, а не к сравнению разных наборов прошлых этапов. '
       'У сбалансированного варианта снижение ложных DONE статистически не подтверждено: интервал парной разности пересекает ноль.', '',
       f'Выполнены два продолжения по4000 обновлений на двух B200. Выбрано **{chosen["run"]}, шаг {chosen["step"]}**, '
       'только по новому development. Родитель был допустимым вариантом шага0. Основное сравнение — один заранее выбранный кандидат и неизменённый родитель.', '',
       '## Что произошло в исходных19 эпизодах','',
       f'Это {analysis["unique_conditions"]} разных условий. Во всех19 финальный код соответствовал неверной первоначальной гипотезе. '
       f'В {analysis["initially_correct"]} эпизодах начальный код уже был правильным, затем сеть испортила его. '
       f'Отказ самопроверки наблюдался в {analysis["with_any_gate_rejection"]} эпизодах; '
       f'в {analysis["with_correct_code_rejected"]} проверка отклоняла действительно правильный код. '
       f'Причины: `{json.dumps(analysis["categories"],ensure_ascii=False)}`.', '',
       'Покомпонентный разбор с условиями и гипотезами: SELF_CHECK_19_ANALYSIS.md. '
       'Он получен воспроизведением всех19 историй в настоящем эмуляторе с проверкой каждого входного промпта.', '',
       '## Что изменилось в обучении','',
       'Добавлены реальные ошибочные состояния, исходные формулировки11 задач и новые перефразировки, '
       'задачи по неверным гипотезам как правильным запросам и200 близких примеров с другими числами и регистрами. '
       'DeepSeek независимо переводила русские формулировки обратно в формулы; исходный AST в обратный запрос не передавался. '
       'Численные цели и переходы проверены ROM.', '',
       'В самопроверке сохранён прежний протокол: первоначальная гипотеза фиксирована и отдельного действия для её замены нет. '
       'Если правильный код конфликтует с этой гипотезой, принятый корректный DONE может быть недостижим. '
       'Учебный ответ после наблюдаемого конфликта — сохранить правильную программу и UNSURE. '
       'UNSURE не считается успешным DONE. Обоснованный отказ проверки на неправильном коде учит WRITE → RUN → DONE.', '',
       'До появления обратной связи скрытая правильность гипотезы не меняет метку действия: '
       'одинаковые видимые состояния с правильным кодом получают одинаковый DONE. '
       'Таким образом, конфликт не угадывается по скрытому полю или искусственному счётчику бюджета.', '',
       f'Учебных состояний {l["rows"]}, допустимых по длине {prep["valid_lessons"]}. '
       f'Статистика курса: `{json.dumps(l["details"],ensure_ascii=False)}`.', '',
       'Каждый batch содержит10 строк перевода,4 обычных исправления,6 исправлений с обратной связью самопроверки, '
       '4 RUN,4 DONE,3 UNSURE для наблюдаемого конфликта и1 UNSURE для исчерпанного бюджета. '
       'Сохраняются парные перестановки таблиц констант и вспомогательные задания копирования числа.', '',
       '## Новый закрытый тест Q4','', '| Метрика | Родитель | Продолжение |','|---|---:|---:|',
       f'| Правильная программа за одну WRITE | {frac(stats["parent"]["primary"])} | {frac(stats["spec"]["primary"])} |']
    if 'development_adapter_strength_recovery'in stats:
        insertion=lines.index('## Что произошло в исходных19 эпизодах')
        alpha=chosen.get('recovery_alpha')
        text=('Полные адаптеры после обучения не прошли контроль сохранения навыков. До открытия closed '
          'дополнительно зафиксирована проверка сил25%,50%,75%: параметры факторов rank16 и строк действий '
          'интерполируются между исходным и дообученным состоянием, затем заново вычисляется настоящий Q4. '
          'Правило выбора не менялось, дополнительных обновлений SGD нет. '
          f'Выбранная сила адаптации: {alpha if alpha is not None else "исходное состояние или полный чекпойнт"}. '
          'Это отдельная настройка на development после первоначального плана; закрытый экзамен при ней не вызывался.')
        lines[insertion:insertion]=[text,'']
    for family in new['primary']['families']:
        lines.append(f'| {family} | {frac(old["primary"]["families"][family])} | {frac(new["primary"]["families"][family])} |')
    lines += ['', '| Отладка / версия | Успех | DONE | Ложные DONE | Доля ошибок среди DONE | Верный код с UNSURE |',
       '|---|---:|---:|---:|---:|---:|']
    for gate in ['self','raw','permuted_raw']:
        for name,report in reports.items():
            v=stats[name][gate];rate='—'if v['false_DONE_fraction']is None else f'{100*v["false_DONE_fraction"]:.1f}%'
            safe=sum(x['abstained']and x['program_correct']for x in report[gate]['records'])
            lines.append(f'| {gate} / {name} | {frac(v)} | {v["DONE"]} | {v["false_DONE"]} | {rate} | {safe} |')
    lines += ['', 'self использует собственную первоначальную гипотезу модели, не эталон условия. '
       'raw оставляет решение о DONE модели. permuted_raw использует полностью перемешанную таблицу. '
       'Для успешного завершения требуются верный код на отдельных аудиторских входах, оба публичных запуска текущей редакции и принятый DONE. '
       'Половина эпизодов начинается с правильного кода, половина — с ошибочного; это отдельная способность от генерации с пустой программы.', '',
       f'В парном сравнении на новом self-экзамене устранены {stats["self_paired_transitions"]["old_false_DONE_removed"]} ложных DONE родителя, '
       f'но появились {stats["self_paired_transitions"]["new_false_DONE_introduced"]} новых. '
       f'Приобретено {stats["self_paired_transitions"]["new_successes"]} правильных завершений, '
       f'потеряно {stats["self_paired_transitions"]["lost_successes"]}.', '',
       '| Причины оставшихся self-ошибок | Родитель | Продолжение |','|---|---:|---:|']
    for key in stats['spec']['self_diagnosis']:lines.append(f'| {key} | {stats["parent"]["self_diagnosis"][key]} | {stats["spec"]["self_diagnosis"][key]} |')
    lines += ['', '## Контролируемые проверки обратной связи','',
       'Это отдельная диагностика, не основной self-экзамен: для пары «неверный код / правильная гипотеза» '
       'и пары «правильный код / неверная гипотеза» заранее выполняется настоящий DONE и получается реальный отказ. '
       'Модель видит только обычное условие, код, результаты эмулятора и сообщение проверки. Эталон используется только для построения сценария и оценки.', '',
       '| Метрика | Родитель | Продолжение |','|---|---:|---:|']
    for name in ['valid_feedback_success','wrong_hypothesis_false_DONE','safe_conflict_exits']:
        a=old['controlled_checks']['summary'];c=new['controlled_checks']['summary']
        denominator='valid_feedback_total'if name=='valid_feedback_success'else'wrong_hypothesis_total'
        lines.append(f'| {name} | {a[name]}/{a[denominator]} | {c[name]}/{c[denominator]} |')
    lines += ['', '## Возврат к исходным19 ошибкам','',
       'Это учебная регрессия, а не новые закрытые задачи. Первоначальные неправильные гипотезы намеренно оставлены прежними для обеих моделей. '
       'Безопасным исходом считается правильный финальный код с UNSURE. Он не приписывается к успешным DONE. '
       'Отдельно проверяется перевод11 исходных условий заново.', '', '| Метрика | Родитель | Продолжение |','|---|---:|---:|']
    for field in ['false_DONE','safe_correct_code_UNSURE','correct_final_code','accepted_DONE']:
        a,c=stats['retired19']['parent']['summary'],stats['retired19']['spec']['summary']
        lines.append(f'| {field} | {a[field]}/{a["total"]} | {c[field]}/{c["total"]} |')
    a,c=stats['retired19']['parent']['translation'],stats['retired19']['spec']['translation'];lines.append(f'| Новый перевод11 старых условий | {frac(a)} | {frac(c)} |')
    lines += ['', '## Сохранение прежних навыков','', '| Метрика | Родитель | Продолжение |','|---|---:|---:|']
    for mode in ['extras','full','distractors']:lines.append(f'| Таблица {mode} | {frac(old["pool_views"][mode]["summary"])} | {frac(new["pool_views"][mode]["summary"])} |')
    lines.append(f'| Полный RUN → DONE | {frac(old["navigation"]["summary"],"cycle_pass")} | {frac(new["navigation"]["summary"],"cycle_pass")} |')
    for a,c in zip(old['short_regressions'],new['short_regressions']):lines.append(f'| {a["task"]} | {a["passed"]} | {c["passed"]} |')
    lines += ['', '## Оценка и воспроизводимость','', '| Набор | Деревьев | Условий |','|---|---:|---:|']
    for name,v in stats['data'].items():lines.append(f'| {name} | {v["trees"]} | {v["questions"]} |')
    if 'development_adapter_strength_recovery'in stats:
        lines += ['', '| Дополнительный контроль | Сила | Сохранение навыков | Self ложных DONE | Self успехов |', '|---|---:|---:|---:|---:|']
        for run,value in stats['development_adapter_strength_recovery']['runs'].items():
            for row in value['results']:
                k=row['key'];lines.append(f'| {run} | {row["alpha"]} | {k[0]} | {-k[2]} | {k[3]} |')
    lines += ['', 'Новый closed исключает сигнатуры сохранённых train/development/closed трёх предыдущих семантических раундов и текущего train. '
       'Отдельные числовые литералы и целевые сочетания операций удержаны из текущего обучения. '
       'Учитываются коммутативность +/* и несущественный угловой режим, но не все алгебраические тождества. '
       'Проверка не охватывает всю историю исходной модели.', '',
       'Правило выбора зафиксировано до SGD: обычная точность, raw- и self-успех сохраняются в пределах3п.п. от родителя, '
       'худшая перестановка таблицы — в пределах5п.п.; навигация и исправления после обоснованного отказа — в пределах одного эпизода; '
       'известные синусы — без потерь. Затем приоритет получают меньше ложных self-DONE, больше self-успехов и безопасных выходов из конфликта. '
       'Так простое увеличение числа UNSURE не получает преимущество при потере правильных завершений.', '',
       '| Парная разность, продолжение минус родитель | п.п. | 95% bootstrap по задачам |','|---|---:|---:|']
    for name,v in stats['paired'].items():
        lo,hi=v['bootstrap_95'];lines.append(f'| {name} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} |')
    if 'supplementary_self_profile'in stats:
        extra=stats['supplementary_self_profile'];s=extra['summary'];p=extra['policy']
        lines += ['', '## Дополнительный профиль самопроверки','',
            'Отдельно проверен seed-b, шаг4000, сила75%. Он выбран по development: '
            '0 ложных self-DONE и114 правильных завершений против6 и110 у родителя. '
            'Обычная отладка на development потеряла6/128 успехов и нарушила исходный допуск3п.п., '
            'поэтому этот профиль не заменяет выбранный сбалансированный вариант.', '',
            'Дополнительная проверка зафиксирована после генерации основных closed-ответов, '
            'но до просмотра их метрик агентом. Все веса и это решение определены по development; '
            'новых градиентных шагов, изменений правила основного выбора и подбора по closed не было. '
            'Это дополнительный анализ, а не часть первоначального плана.', '',
            '| Метрика нового закрытого Q4 | Родитель | Сбалансированный | Самопроверка75% |',
            '|---|---:|---:|---:|']
        for panel,field,label in [('primary','passed','Программа за одну WRITE'),('self','passed','Правильный self-DONE'),
                ('self','false_DONE','Ложный self-DONE'),('raw','passed','Правильный raw-DONE'),
                ('raw','false_DONE','Ложный raw-DONE'),('permuted_raw','passed','Отладка с перестановкой констант')]:
            values=[stats['parent'][panel],stats['spec'][panel],s[panel]]
            lines.append('| '+label+' | '+' | '.join(f'{v[field]}/{v["total"]}'for v in values)+' |')
        for field,label,denom in [('valid_feedback_success','Исправление после обоснованного отказа','valid_feedback_total'),
                ('wrong_hypothesis_false_DONE','Ложный DONE при навязанной неверной гипотезе','wrong_hypothesis_total'),
                ('safe_conflict_exits','Сохранён правильный код с UNSURE после конфликта','wrong_hypothesis_total')]:
            values=[stats['parent']['controlled_checks'],stats['spec']['controlled_checks'],s['controlled_checks']]
            lines.append('| '+label+' | '+' | '.join(f'{v[field]}/{v[denom]}'for v in values)+' |')
        lines += ['', '| Старые19 учебных эпизодов | Родитель | Сбалансированный | Самопроверка75% |','|---|---:|---:|---:|']
        for field in ['false_DONE','safe_correct_code_UNSURE','correct_final_code']:
            values=[stats['retired19']['parent']['summary'],stats['retired19']['spec']['summary'],extra['retired19']['summary']]
            lines.append('| '+field+' | '+' | '.join(f'{v[field]}/{v["total"]}'for v in values)+' |')
        lines += ['', '| Дополнительный профиль минус родитель | п.п. | 95% bootstrap по задачам |','|---|---:|---:|']
        for name,v in extra['paired'].items():
            lo,hi=v['bootstrap_95'];lines.append(f'| {name} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} |')
        lines += ['', 'Все результаты дополнительного профиля сохранены, включая обычную отладку, '
            'перестановки констант и контролируемые конфликты. Ноль ошибок на development '
            'не означает ноль ошибок на новых задачах. Артефакты: safety/closed.json и export/safety.', '',
            f'На новом экзамене этот профиль дал {s["self"]["false_DONE"]} ложных self-DONE '
            f'и {s["self"]["passed"]} правильных завершений против {b["false_DONE"]} '
            f'и {b["passed"]} у родителя. Улучшение старых учебных ошибок не перенеслось '
            'в надёжную самопроверку на новых условиях.', '']
    lines += ['', 'Отладочные эпизоды группируются по условию; правильный и ошибочный старт не считаются независимыми задачами. '
       'Интервалы относятся к задачам для одного выбранного кандидата, а не к разбросу обучения между сидами.', '',
       '## Экспорт и границы','', '| Версия | MKA, байт | Native-проб |','|---|---:|---:|']
    for name,v in read(root/'native-verification.json')['models'].items():lines.append(f'| {name} | {v["mka_bytes"]} | {v["probes"]} |')
    lines += ['', 'Сохранены3 022 080 параметров,318 208 обучаемых коэффициентов rank16, контекст1024 и прежние шесть действий. '
       'Q4 используется при каждом прямом проходе; вычисления и KV — FP32. Входной русский словарь и неадаптированные тензоры проверены отдельно. '
       'Перед SGD проверено точное исходное Q4-состояние на B200, после — совпадение экспорта и потоков B200/CPU/C++ decoder, включая сообщения самопроверки.', '',
       'Протокол самопроверки и его правила не менялись. Курс ограничен прямолинейной арифметикой и необязательной записью результата. '
       'Конечные проверки с допуском2e-6 не доказывают правильность для произвольных программ и не исключают все ошибки понимания языка. '
       'Работа выполнена на компьютере и сервере; физические скорость и пиковая память PicoCalc не измерялись, основной профиль и прошивка не заменены. '
       'Свои учебные контейнеры завершены.', '',
       f'Артефакты: {root}; comparison.json; parent/closed.json и spec/closed.json; export/spec/{{hf,model.mkqb,model.mka}}. '
       'Подробные старые регрессии: {parent,spec}/retired19-regression.json.', '']
    report=HERE/'SPEC_SELF_CHECK_RESULTS.md'
    text=re.sub(r'(?<=[А-Яа-яЁё])(?=\d)|(?<=\d)(?=[А-Яа-яЁё])',' ','\n'.join(lines))
    report.write_text(text)
    write(root/'report-receipt.json',{'sha256':sha(report),'optimizer_updates':8000,'closed_used_for_selection':False})
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
