"""Publish paired Q4 results without treating repeated layouts as new tasks."""
import argparse
import collections
import json
from pathlib import Path
import random
import statistics
from ba_common import HERE,read,write,sha


def cluster_difference(a,b,metric,cluster='id'):
    def group(rows):
        result=collections.defaultdict(list)
        for r in rows:result[r[cluster]].append(float(metric(r)))
        return {k:statistics.mean(v)for k,v in result.items()}
    x,y=group(a),group(b);assert set(x)==set(y);delta=[y[k]-x[k]for k in sorted(x)];n=len(delta);rng=random.Random(26110853)
    samples=sorted(statistics.mean(rng.choices(delta,k=n))for _ in range(4000))
    return {'clusters':n,'difference':statistics.mean(delta),'bootstrap_95':[samples[99],samples[3899]],
        'cluster':cluster,'one_selected_model_not_training_seed_interval':True}


def summary(report):
    result={k:v['summary']for k,v in report.items()if isinstance(v,dict)and'summary'in v}
    result['pool_views']={k:v['summary']for k,v in report['pool_views'].items()}
    for gate in ['raw','self','permuted_raw']:
        if gate not in report:continue
        s=result[gate]=dict(result[gate]);records=report[gate]['records']
        s['correct_DONE_public_ineligible']=sum(r['finished']and r['program_correct']and not r['eligible']for r in records)
        s['false_DONE_fraction']=s['false_DONE']/s['DONE']if s['DONE']else None
    result['families']=report['primary']['families'];result['panels']=report['primary']['panels']
    result['known_short_probes']=[{'task':r['task'],'passed':r['passed']}for r in report['short_regressions']]
    return result


def frac(v,key='passed'):return f'{v[key]}/{v["total"]}'


def main(root):
    assert read(root/'complete.json')['completed']and read(root/'native-verification.json')['complete']
    assert read(root/'postflight.json')['all_frozen_files_verified']
    selection=read(root/'preselected.json');assert not selection['closed_used_for_selection']
    reports={a:read(root/a/'closed.json')for a in ['parent','spec']};old,new=reports['parent'],reports['spec']
    stats={'optimizer_updates':8000,'selection':selection,'data':read(root/'teacher-frozen.json')['counts'],
        'parent':summary(old),'spec':summary(new),'paired':{
          'primary':cluster_difference(old['primary']['records'],new['primary']['records'],lambda r:r['program_correct']),
          'raw_success':cluster_difference(old['raw']['records'],new['raw']['records'],lambda r:r['pass'],'task_id'),
          'raw_false_DONE':cluster_difference(old['raw']['records'],new['raw']['records'],lambda r:r['finished']and not r['program_correct'],'task_id')},
        'development_curves':{run:[{'step':step,'summary':summary(read(root/run/f'development-{step}.json'))}
             for step in [1000,2500,4000]]for run in ['seed-a','seed-b']}}
    pool_ids={r['id']for r in new['pool_views']['full']['records']};pool_totals={}
    for name,report in reports.items():
        maps={mode:{r['id']:r['program_correct']for r in v['records']}for mode,v in report['pool_views'].items()}
        ordinary={r['id']:r['program_correct']for r in report['primary']['records']if r['id']in pool_ids}
        assert all(set(m)==pool_ids for m in maps.values())
        all_correct={k:ordinary[k]and all(m[k]for m in maps.values())for k in pool_ids}
        pool_totals[name]={'default':{'total':len(pool_ids),'passed':sum(ordinary.values())},
             **{k:v['summary']for k,v in report['pool_views'].items()},'all_views':{'total':len(pool_ids),'passed':sum(all_correct.values())}}
    stats['matched_pool_cohort']=pool_totals
    stats['paired']['full_pool']=cluster_difference(old['pool_views']['full']['records'],new['pool_views']['full']['records'],lambda r:r['program_correct'])
    b,n=stats['parent']['raw'],stats['spec']['raw'];bp,np=stats['parent']['primary'],stats['spec']['primary']
    stats['both_objectives_improved_on_closed']=(n['false_DONE']<b['false_DONE']and
        min(x['passed']/x['total']for x in stats['spec']['pool_views'].values())>min(x['passed']/x['total']for x in stats['parent']['pool_views'].values())and
        np['passed']/np['total']>=bp['passed']/bp['total']-.03 and n['passed']/n['total']>=b['passed']/b['total']-.03)
    if(root/'user-probes.json').exists():stats['user_probes']=read(root/'user-probes.json')
    if(root/'canonical-order-eval.json').exists():
        h=read(root/'canonical-order-eval.json')
        stats['optional_canonical_harness']={k:v for k,v in h.items()if k!='models'}
        stats['optional_canonical_harness']['models']={name:{mode:{k:v for k,v in value.items()if k!='records'}for mode,value in values.items()}for name,values in h['models'].items()}
    write(root/'comparison.json',stats)
    chosen=selection['selected'];lessons=read(root/'lessons-frozen.json');prepared=read(root/'prepared.json')
    lines=['# SPEC Q4: ложные DONE и порядок констант', '',
      f'На новом закрытом экзамене прежняя SPEC решила {frac(bp)}, продолженная — {frac(np)}. '
      f'Ложных DONE в raw: {b["false_DONE"]} → {n["false_DONE"]}; правильных завершений: {b["passed"]} → {n["passed"]} из {n["total"]}. '
      f'В raw обе цели улучшились при сохранении покрытия: {stats["both_objectives_improved_on_closed"]}. '
      'Это результат на конечном наборе, а не гарантия правильного DONE для произвольного запроса.', '',
      f'В режиме self есть ухудшение: ложных DONE {stats["parent"]["self"]["false_DONE"]} → {stats["spec"]["self"]["false_DONE"]}. '
      'Поэтому новое обучение улучшило генерацию и обычную отладку, но не устранило проблему самопроверки по неподтверждённой гипотезе. '
      'Её нельзя считать независимой проверкой смысла задания.', '',
      'Продолжалась выбранная SPEC прошлого этапа, шаг1500. Выполнены два запуска по4000 обновлений на двух B200; '
      'различались случайные выборки и перестановки. Один кандидат выбран по новому development; '
      'только он и неизменённый родитель проверены на новом closed. Закрытый тест не использовался для выбора весов.', '',
      f'Выбрано: **{chosen["run"]}, шаг {chosen["step"]}**. Вариант шага0 означает сохранение родителя, если контроль не подтвердил улучшения.', '',
      '| Q4, одна попытка WRITE | Родитель | Продолжение |', '|---|---:|---:|',
      f'| Все новые условия | {frac(bp)} | {frac(np)} |']
    for family in new['primary']['families']:
        lines.append(f'| {family} | {frac(old["primary"]["families"][family])} | {frac(new["primary"]["families"][family])} |')
    lines += ['', 'В этой проверке действие WRITE задано принудительно; оценивается перевод условия и исполнение полученной программы на отдельных аудиторских входах. '
       'Сохранение всех неназванных регистров и остановка входят в успех.', '',
       '## Одна задача, разные таблицы констант', '',
       'На одном и том же поднаборе числовых условий сравниваются четыре вида таблицы. В extras меняются только дополнительные позиции; '
       'в full — все позиции, включая базовые. Для этих двух вариантов набор значений полностью совпадает с default. '
       'В distractors дополнительно вставлены отвлекающие числа. Задачи, текущие программы и эталоны пересобраны с новыми индексами; '
       'реальный машинный код сохраняется побайтово. Эти варианты не считаются независимыми новыми задачами.', '',
       '| Вариант таблицы | Родитель | Продолжение |', '|---|---:|---:|']
    for mode in ['default','extras','full','distractors','all_views']:
        lines.append(f'| {mode} | {frac(pool_totals["parent"][mode])} | {frac(pool_totals["spec"][mode])} |')
    lines += ['', 'all_views — число условий, решённых правильно во всех четырёх вариантах одновременно. '
       'Для extras часть задач с константами только из базового списка не меняет таблицу; число реально изменённых таблиц есть в подробных JSON.', '',
       '## Отладка и завершение', '',
       'raw — модель сама выбирает действие. self — прежний механический фильтр сверяет код с собственной гипотезой модели; '
       'он не получает правильную спецификацию запроса. permuted_raw — отладка с полной перестановкой таблицы. '
       'Каждое условие даётся с правильным и ошибочным начальным кодом; успех из пустой программы этим тестом не измеряется. '
       'Для успеха нужны верный код на аудиторских входах, DONE и оба обязательных запуска текущей редакции.', '',
       '| Режим / версия | Успех | DONE | Ложные DONE | Ошибочных среди DONE | Правильный код, непроверенный DONE | Исправлено плохих стартов |',
       '|---|---:|---:|---:|---:|---:|---:|']
    for gate in ['raw','self','permuted_raw']:
        for name in ['parent','spec']:
            v=stats[name][gate];rate='—'if v['false_DONE_fraction']is None else f'{100*v["false_DONE_fraction"]:.1f}%'
            lines.append(f'| {gate} / {name} | {frac(v)} | {v["DONE"]} | {v["false_DONE"]} | {rate} | {v["correct_DONE_public_ineligible"]} | {v["wrong_starts_repaired"]}/{v["wrong_starts"]} |')
    lines += ['', 'Ложный DONE означает фактически неверный финальный код. Он не смешивается с верным кодом, для которого пропущены публичные запуски. '
       'Падение ошибок без сохранения числа правильных завершений не считается достаточным улучшением. '
       'Механическая проверка относительно ошибочного понимания условия по-прежнему может пропускать неверные решения.', '',
       '| Навигация после WRITE | Родитель | Продолжение |', '|---|---:|---:|']
    for case in [0,1]:
        lines.append(f'| Следующий RUN {case:02X} | {frac(old["navigation"]["summary"]["by_case"][str(case)],"next_step_correct")} | {frac(new["navigation"]["summary"]["by_case"][str(case)],"next_step_correct")} |')
    lines.append(f'| Полный RUN → DONE | {frac(old["navigation"]["summary"],"cycle_pass")} | {frac(new["navigation"]["summary"],"cycle_pass")} |')
    lines += ['', '## Парная неопределённость', '', '| Метрика, продолжение минус родитель | Разность, п.п. | 95% bootstrap, п.п. | Единиц |', '|---|---:|---:|---:|']
    for name,v in stats['paired'].items():
        lo,hi=v['bootstrap_95'];lines.append(f'| {name} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} | {v["clusters"]} |')
    lines += ['', 'Для отладки bootstrap группируется по условию, объединяя правильный и ошибочный старт. '
       'Повторные перестановки таблицы не увеличивают число независимых условий. '
       'Это интервалы по задачам для одного выбранного кандидата, а не оценка разброса обучения между сидами.', '',
       '## Курс и защита теста', '', '| Набор | Деревьев | Условий |', '|---|---:|---:|']
    for name,v in stats['data'].items():lines.append(f'| {name} | {v["trees"]} | {v["questions"]} |')
    lines += ['', 'Прошлый экзамен явно снят с роли теста: его ошибочные задачи вошли в обучение после новой проверенной формулировки. '
       'Новое closed не содержит сигнатур train/development/closed двух предыдущих семантических раундов и нового train. '
       'Удаление сигнатур учитывает коммутативность +/* и несущественный угловой режим, но не все алгебраические тождества. '
       'Отдельные числа и целевые пары операций удержаны из текущего обучения; это не заявление об их отсутствии во всей истории основания модели.', '',
       'DeepSeek-V4.1-Flash создавала русские формулировки и отдельно восстанавливала формулу без доступа к исходному AST. '
       'Латинские имена функций в вопросах отбрасывались автоматически. Учитель не задавал правильность DONE: её определяли компилятор и реальный ROM.', '',
       f'Учебных состояний {lessons["rows"]}, допущено по длине {prepared["valid_lessons"]}. '
       f'Детали построения: `{json.dumps(lessons["details"],ensure_ascii=False)}`.', '',
       'Первые600 обновлений уделяют больше места коротким заданиям на привязку числа к индексу. '
       'Далее каждый batch содержит12 строк перевода,8 исправления,4 RUN,4 DONE и4 UNSURE. '
       'Примеры перевода/исправления подаются парами с разными таблицами; перестановки пересоздаются при каждом выборе. '
       'Часть исправлений — реальные ошибки родителя, часть — пары с одним наблюдаемым кодом и разными условиями. '
       'Положительные DONE имеют верный код и необходимые запуски; UNSURE обучается в реально исчерпанном бюджете.', '',
       'Размер и протокол сохранены: 3 022 080 параметров, rank16 адаптеры,318 208 обучаемых коэффициентов, контекст1024; '
       'Q4 на каждом прямом проходе, вычисления FP32. Нового критика, DPO или штрафа за DONE нет. '
       'Начальные адаптеры совпадают с прежним выбранным SPEC; перед SGD на B200 проверены точные исходные Q4 payload. '
       'Русский входной словарь и тензоры вне адаптеров проверены отдельно.', '',
       'Правило выбора зафиксировано до SGD. Оно сохраняет обычную точность и число успешных отладок в пределах3п.п. от родителя, '
       'навигацию — в пределах одного эпизода, известные запросы синуса — без потерь. '
       'Преимущество отдаётся совместному улучшению: не больше ложных DONE и минимум+10п.п. по худшему виду таблицы. '
       'Далее минимизируются ложные DONE и учитываются худшая точность таблиц и число правильных завершений. '
       'Родитель включён как вариант шага0. Закрытый экзамен не менял это правило.', '',
       'Известные короткие запросы, не являющиеся новым экзаменом:', '', '| Запрос | Родитель | Продолжение |', '|---|---:|---:|']
    for a,b in zip(old['short_regressions'],new['short_regressions']):lines.append(f'| {a["task"]} | {a["passed"]} | {b["passed"]} |')
    if 'optional_canonical_harness'in stats:
        h=stats['optional_canonical_harness'];models=h['models']
        lines += ['', '## Отдельный прототип harness: канонизация таблицы', '',
           'Файлы bb_canonical.py и bb_session.py приводят доступные константы к стабильному порядку перед вызовом модели '
           'и переводят индексы ответа обратно. Значения не добавляются и не удаляются; текущий HEX перенумеровывается без изменения машинного кода. '
           'Код не получает эталонной спецификации задания. Это отдельная диагностическая проверка harness после выбора весов; '
           'она не включена в основной результат обучения выше.', '',
           '| Та же числовая когорта, канонизация harness | Родитель | Продолжение |', '|---|---:|---:|']
        for mode in ['extras','full']:lines.append(f'| {mode} | {frac(models["parent"][mode])} | {frac(models["spec"][mode])} |')
        prompts=sum(v['raw_full_table']['prompts_identical']for v in models.values())
        lines += ['', f'Подтверждено точное равенство {prompts} входных запросов модели при воспроизведении 512 отладочных эпизодов '
           'с полностью переставленной таблицей и тем же исходным машинным кодом. Поэтому использовались уже полученные потоки токенов; '
           'каждое действие и конечный код повторно прогнаны настоящим ROM. Это не дополнительные независимые пробы нейросети. '
           'Поведение с новым порядком становится таким же, как с каноническим, включая оставшиеся ошибки и ложные DONE. '
           'Добавление новых отвлекающих значений меняет набор таблицы и этой эквивалентностью не покрывается.', '',
           'Готовая обёртка для моделирования: bb_session.Session; локальные предложения с необязательной внешней таблицей: bb_chat.py --pool JSON. '
           'Эта обёртка убирает зависимость от перестановки таблицы, но не исправляет неверное понимание задания.']
    lines += ['', '## Экспорт', '', '| Версия | MKA, байт | Native-проб | KV1024, байт | Workspace, байт |', '|---|---:|---:|---:|---:|']
    for name,v in read(root/'native-verification.json')['models'].items():lines.append(f'| {name} | {v["mka_bytes"]} | {v["probes"]} | {v["cache_bytes"]} | {v["workspace_bytes"]} |')
    lines += ['', 'Проверены сохранённый master → те же Q4 байты и совпадение потоков на B200,CPU иC++ decoder, включая переставленные таблицы. '
       'Native-пакет родителя совпадает с прошлым экспортом. Полный отчёт проверок: native-verification.json и postflight.json. '
       'Свои контейнеры завершены, физические скорость и пиковая память PicoCalc не измерялись; прошивка и основной профиль не заменялись.', '',
       'Курс ограничен прямолинейной арифметикой и необязательной записью результата. Проверка конечная, с допуском2e-6. '
       'Коррелированные ошибки учителя при понимании русского текста полностью не исключены. '
       'Успех синтетического теста не доказывает способность решать произвольные программы, циклы или ветвления.', '',
       f'Артефакты: {root}. Метрики: comparison.json; ответы: parent/closed.json иspec/closed.json; '
       'модели: export/{parent,spec}/{hf,model.mkqb,model.mka}. Локальный запуск использует прежний az_chat.py и тот же wire-format.json.', '']
    report=HERE/'SPEC_GROUNDING_RESULTS.md';report.write_text('\n'.join(lines));write(root/'report-receipt.json',{'sha256':sha(report),'closed_used_for_selection':False,'optimizer_updates':8000})
    print(json.dumps(stats,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
