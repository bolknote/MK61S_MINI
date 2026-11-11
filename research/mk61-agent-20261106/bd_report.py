"""Attribute errors to interpretation and control on the already opened cohort."""
import argparse
import collections
import json
from pathlib import Path
from bd_common import ROOT,HERE,ARMS,read,rows,write,sha
from ay_eval import episode_metrics
from ba_report import cluster_difference
from ar_spec import spec_text


LABELS={'own_actor':'Своя SPEC + агент','oracle_actor':'Эталонная SPEC + агент',
    'own_mechanical':'Своя SPEC + механический контроллер','oracle_mechanical':'Эталонная SPEC + механический контроллер'}

LANGUAGE_FLAGS=[
    ('bc:closed:known:constant:0021','Неявная граница аргумента слова «квадрат».',
        'Вычисли квадрат разности чисел0.375 и28.25. Результат запиши в R4.'),
    ('bc:closed:known:register:0001','Фраза «логарифм от RD умножить на50» не отделяет умножение после логарифма от умножения внутри аргумента.',
        'Вычисли десятичный логарифм RD. Умножь полученный результат на50.'),
    ('bc:closed:known:register:0033','Оборот «возведённое в степень RD» допускает разное присоединение. Предсказание сети при этом пропускает RD и остаётся ошибочным.',
        'Возведи1.25 в степень24, затем полученное число в степень RD. Раздели R2 на окончательный результат.'),
    ('bc:closed:known:register:0036','Неявная граница аргумента функции знака. Предсказание сети не совпадает и с простой альтернативой sign(R2)+cos(0.95).',
        'Сложи R2 и косинус0.95 в градах. Определи знак полученной суммы. Запиши результат в RD.'),
    ('bc:closed:known:register:0038','Фраза «возведён в степень с основанием3.5 и показателем…» не соответствует ясно сохранённому дереву; требуется переписать условие.',
        'Возведи модуль R9 в степень, равную десятичному логарифму3.5. К полученному значению прибавь натуральный логарифм22.'),
    ('bc:closed:novel:numeric:0014','Нечёткая связка «делить на R4 и минус8.75». Сеть дополнительно подменяет R4 на RE, что неоднозначность не объясняет.',
        'Раздели21.25 на значение регистра R4. Из полученного частного вычти8.75. Запиши результат в R1.')]


def differences(actual,target):
    found=set()
    def compare(a,b):
        if a==b:return
        if isinstance(a,str)and isinstance(b,str):found.add('register');return
        if isinstance(a,dict)and isinstance(b,dict):found.add('literal_or_literal_kind');return
        if isinstance(a,list)and isinstance(b,list):
            if a[0]!=b[0]:found.add('operation')
            if len(a)==len(b)==3 and a[0]==b[0]and a[1]==b[2]and a[2]==b[1]:found.add('argument_order')
            for x,y in zip(a[1:],b[1:]):compare(x,y)
            if len(a)!=len(b):found.add('tree_structure')
            return
        found.add('tree_structure_or_leaf_type')
    if actual is None:return ['unavailable_spec']
    compare(actual['X'],target['X'])
    if set(actual.get('writes',{}))!=set(target.get('writes',{})):found.add('destination')
    if actual['angle']!=target['angle']:found.add('angle')
    return sorted(found)


def main(root):
    complete=read(root/'complete.json');assert complete['complete']and complete['optimizer_updates']==0
    assert read(root/'native-verification.json')['complete']
    assert read(root/'postflight.json')['own_containers_running']==[]
    reports={a:read(root/(a+'.json'))for a in ARMS};jobs=rows(root/'jobs.jsonl');goals={g['id']:g for g in rows(root/'groups.jsonl')}
    stats={'optimizer_updates':0,'teacher_calls':0,'new_closed_exam':False,'unique_conditions':128,
        'episodes_per_arm':256,'source_Q4_sha256':read(root/'frozen.json')['source_Q4_sha256'],
        'arms':{a:r['summary']for a,r in reports.items()},'generations':complete['generations'],
        'replay':read(root/'baseline-replay-verification.json'),'preflight':read(ROOT/'preflight.json'),
        'conditional':{},'paired':{},'primary_error_features':{},'examples':[]}
    old_primary=read(root/'baseline.json')['primary'];bad_primary=[r for r in old_primary['records']if not r['program_correct']]
    features=collections.Counter()
    for r in bad_primary:features.update(differences(r['declared_spec'],goals[r['id']]['spec']))
    stats['primary_error_features']={'total':len(bad_primary),'overlapping_syntactic_features':dict(features),
        'correct_numeric_intent_but_bad_code':sum(r['intent']['tested_equal']for r in bad_primary),
        'not_a_causal_or_semantic_classification':True}
    stats['language_review']={'reviewed_error_conditions':len(bad_primary),'posthoc_review_only':True,
        'reviewer':'Codex','not_an_independent_human_annotation':True,'metrics_relabelled_or_filtered':False,
        'flags':[{'id':i,'task':goals[i]['task'],'reason':reason,'suggested_clearer_wording':rewrite}for i,reason,rewrite in LANGUAGE_FLAGS]}
    write(root/'language-review.json',stats['language_review'])
    task_jobs={j['task_id']:j for j in jobs};stats['initial_intent']={'total':len(task_jobs),
        'correct':sum(j['own_spec_correct']for j in task_jobs.values()),'available':sum(j['own_spec']is not None for j in task_jobs.values())}
    for arm,value in reports.items():
        records=value['records'];stats['conditional'][arm]={}
        for name,predicate in [('own_intent_correct',lambda r:r['own_initial_spec_correct']),
                ('own_intent_wrong',lambda r:not r['own_initial_spec_correct']),
                ('initial_code_correct',lambda r:r['initially_correct']),('initial_code_wrong',lambda r:not r['initially_correct'])]:
            chosen=[r for r in records if predicate(r)];stats['conditional'][arm][name]=episode_metrics(chosen)
        bad=[r for r in records if r['finished']and not r['program_correct']]
        visible=lambda r:any('DONE_REJECTED'in h.get('observation','')or'DONE_REJECTED'in h.get('prompt','')for h in r['history'])
        stats['conditional'][arm]['false_DONE_feedback']={'total':len(bad),'with_visible_rejection':sum(visible(r)for r in bad),
            'without_visible_rejection':sum(not visible(r)for r in bad)}
    contrasts=[('gate_given_actor','own_actor','oracle_actor'),('control_given_own_spec','own_actor','own_mechanical'),
        ('control_given_gold_spec','oracle_actor','oracle_mechanical'),('intent_given_mechanical','own_mechanical','oracle_mechanical')]
    for label,a,b in contrasts:
        stats['paired'][label]={'from':a,'to':b,
            'success':cluster_difference(reports[a]['records'],reports[b]['records'],lambda r:r['pass'],'task_id'),
            'false_DONE':cluster_difference(reports[a]['records'],reports[b]['records'],lambda r:r['finished']and not r['program_correct'],'task_id')}
    lookup={a:{r['id']:r for r in v['records']}for a,v in reports.items()}
    old_bad=[r for r in reports['own_actor']['records']if r['finished']and not r['program_correct']]
    example_tasks=set()
    for r in old_bad:
        if r['task_id']in example_tasks:continue
        if len(stats['examples'])==5:break
        example_tasks.add(r['task_id'])
        g=goals[r['task_id']]
        stats['examples'].append({'id':r['id'],'task':g['task'],'own_spec':spec_text(r['declared_spec']),
            'required_spec':spec_text(g['spec']),
            'outcomes':{a:{k:lookup[a][r['id']][k]for k in ['pass','finished','abstained','program_correct']}for a in ARMS}})
    write(root/'comparison.json',stats)
    lines=['# SPEC Q4: разделение понимания и управления','',
        'Диагностика выполнена без обучения, вызовов учителя и выбора новых весов. '
        'Использован прежний выбранный SPEC Q4, seed-a, шаг4000, сила адаптации25%. '
        'Это повторный анализ уже открытого экзамена, а не новая независимая закрытая проверка.', '',
        'Во всех четырёх режимах одинаковы128 условий,256 стартов, текущие программы, таблицы констант, '
        'углы, публичные входы, входы проверяющего и отдельного аудита. Половина стартов правильные. '
        'Повторения одного условия группируются при оценке неопределённости.', '',
        '## Четыре режима','', '| Режим | Правильный принятый DONE | Все DONE | Ложные DONE | Ошибок среди DONE | UNSURE | Лимит/ошибка |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for a in ARMS:
        s=stats['arms'][a];rate='—'if s['false_DONE_fraction']is None else f'{100*s["false_DONE_fraction"]:.1f}%'
        lines.append(f'| {LABELS[a]} | {s["passed"]}/{s["total"]} | {s["DONE"]} | {s["false_DONE"]} | {rate} | {s["abstained"]} | {s["exhausted"]} |')
    lines += ['', 'Своя SPEC взята из исходной одношаговой попытки модели. Эталонная SPEC доступна только '
        'в двух явно диагностических режимах и не является доступным на устройстве источником истины.', '',
        'В режиме агента эталон меняет только приватную спецификацию механического проверяющего. '
        'Само условие и исходный промпт не меняются; правильная формула может попасть в контекст '
        'после настоящего DONE_REJECTED как обычная обратная связь. Это измеряет действие корректного '
        'проверяющего, а не способность агента читать формальную SPEC с самого начала.', '',
        'Механический контроллер проверяет текущий код по предоставленной ему SPEC на обычных входах '
        'проверяющего. Если код не проходит, он компилирует эту SPEC детерминированно, выполняет недостающие '
        'RUN актуальной редакции и запрашивает DONE через прежний gate. Если SPEC недоступна или проверка '
        'не проходит, отвечает UNSURE. Эталон условия и аудиторские входы не используются в выборе его '
        'действий вне явно эталонного режима. Бюджет остаётся12 действий.', '',
        '## Практический вывод','',
        'В пределах данного набора компилятор и механический контроллер обеспечили256/256 правильных '
        'завершений при заданной правильной SPEC. С собственной верной SPEC они завершили220/220 стартов. '
        'Следовательно, для поддерживаемой прямолинейной арифметики полезно сосредоточить модель на '
        'переводе условия в SPEC, а механические действия выполнять кодом.', '',
        'Автоматическое завершение по неподтверждённой SPEC ухудшило ложные DONE с18 до30. '
        'Поэтому готовность исполнения и подтверждение смысла условия должны учитываться отдельно. '
        'Наличие независимой правильной SPEC здесь является диагностическим вмешательством; '
        'сам эксперимент не создал автономный проверяющий русского языка.', '',
        'Следующий учебный эксперимент: сначала очистить формулировки и выделить однозначные '
        'условия; затем сравнить узкое обучение переводу в SPEC текущими адаптерами и полное '
        'дообучение тех же3M при одинаковых данных и новой заранее закрытой оценке. '
        'В этом диагностическом раунде эти обучения не запускались.', '',
        '## Зависимость от исходного понимания','',
        f'Собственная SPEC верна для {stats["initial_intent"]["correct"]}/{stats["initial_intent"]["total"]} условий; '
        f'доступна для {stats["initial_intent"]["available"]}/{stats["initial_intent"]["total"]}.', '',
        '| Режим | Успех при верной исходной SPEC | Успех при неверной исходной SPEC | Исправлены неверные старты | Сохранены и завершены верные старты |',
        '|---|---:|---:|---:|---:|']
    for a in ARMS:
        c=stats['conditional'][a];s=stats['arms'][a];good,bad=c['own_intent_correct'],c['own_intent_wrong']
        lines.append(f'| {LABELS[a]} | {good["passed"]}/{good["total"]} | {bad["passed"]}/{bad["total"]} | '
            f'{s["wrong_starts_repaired"]}/{s["wrong_starts"]} | {s["correct_starts_completed"]}/{s["correct_starts"]} |')
    own_feedback=stats['conditional']['own_actor']['false_DONE_feedback']
    lines += ['', f'У исходного агента {own_feedback["without_visible_rejection"]} из {own_feedback["total"]} '
        'ложных DONE прошли без наблюдаемого отказа. Поэтому уроки реакции на DONE_REJECTED '
        'сами по себе почти не затрагивают эти ошибки.', '',
        '## Парные различия','', '| Изменение режима | Успех, п.п. | 95% интервал | Ложные DONE, п.п. | 95% интервал |',
        '|---|---:|---:|---:|---:|']
    for value in stats['paired'].values():
        s,f=value['success'],value['false_DONE'];interval=lambda v:' … '.join(f'{100*x:+.1f}'for x in v['bootstrap_95'])
        lines.append(f'| {LABELS[value["from"]]} → {LABELS[value["to"]]} | {100*s["difference"]:+.1f} | {interval(s)} | '
            f'{100*f["difference"]:+.1f} | {interval(f)} |')
    lines += ['', 'Интервалы получены bootstrap по128 условиям. Это один фиксированный набор и один '
        'выбранный чекпойнт. Они не оценивают разброс обучения и не учитывают всё разнообразие русских запросов.', '',
        '## Структурные признаки ошибок перевода','',
        f'На исходных398 одношаговых задачах неверных программ: {len(bad_primary)}. '
        'Ниже перечислены пересекающиеся синтаксические различия дерева с эталоном; это описание '
        'результатов, а не независимое причинное объяснение или новая семантическая разметка.', '',
        '```json',json.dumps(stats['primary_error_features'],ensure_ascii=False,indent=2),'```','',
        '## Проверка формулировок перед новым обучением','',
        'После просмотра42 ошибочных одношаговых условий отмечены6 формулировок, требующих '
        'отдельной проверки области действия операций или редакторской правки. Это разбор агентом '
        'после получения результатов, не независимая человеческая разметка и не оценка доли '
        'неоднозначных задач во всём корпусе. Исходные метрики и эталоны не изменены. '
        'Отмеченная неоднозначность не делает каждое ошибочное предсказание допустимым.', '',
        '| Условие | Причина проверки | Предлагаемая ясная формулировка сохранённого эталона |','|---|---|---|']
    for f in stats['language_review']['flags']:
        lines.append(f'| {f["task"]} | {f["reason"]} | {f["suggested_clearer_wording"]} |')
    lines += ['',
        'Например, «десятичный логарифм от RD умножить на50» допускает разное прочтение границы '
        'аргумента. Для нового курса нужно явно отделять log10(RD)*50 от log10(RD*50). '
        'Независимый обратный перевод тем же большим учителем не заменяет такую проверку качества. '
        'Артефакт разбора: language-review.json.', '',
        '## Примеры','']
    for e in stats['examples']:
        lines += [e['task'],'',f'- Требовалось: `{e["required_spec"]}`',f'- Исходная гипотеза: `{e["own_spec"]}`']
        for a in ARMS:
            v=e['outcomes'][a];outcome='правильный DONE'if v['pass']else'ложный DONE'if v['finished']else'UNSURE'if v['abstained']else'лимит/ошибка'
            lines.append(f'- {LABELS[a]}: {outcome}.')
        lines.append('')
    lines += ['## Проверки и границы','',
        'Исходная ветка воспроизведена по сохранённым потокам Q4 с точным совпадением промптов, '
        'токенов, конечных состояний и результатов gate во всех256 эпизодах. '
        'Это проверка воспроизводимости, а не256 новых независимых запусков нейросети. '
        'В эталонной ветке повторно использованы только ответы на побуквенно совпадающие промпты; '
        'новые состояния действительно обработаны неизменённой Q4-моделью.', '',
        f'Свежих уникальных Q4-запросов: {complete["generations"].get("fresh_unique_Q4_prompts",0)}. '
        f'Новых проб B200/CPU/C++: {read(root/"native-verification.json")["fresh_feedback_probes"]}; '
        'в выбранных пробах потоки токенов совпали. Весовой пакет и входной словарь не изменены.', '',
        'Проверка ограничена прямолинейной арифметикой и записью результата в один регистр, '
        'конечными наборами входов и прежним допуском2e-6. Это не доказательство для произвольной '
        'области, ветвлений или циклов. Основной профиль и прошивка не заменены; физических '
        'замеров PicoCalc нет. Все собственные удалённые задачи этого эксперимента завершены.', '',
        f'Артефакты: {root}. Политика: policy.json; результаты: четыре файла *_actor.json и '
        '*_mechanical.json; проверка исходной ветки: baseline-replay-verification.json; '
        'точные новые запросы: new-generations.jsonl. Число обновлений весов:0.', '']
    import re
    text=re.sub(r'(?<=[А-Яа-яЁё])(?=\d)|(?<=\d)(?=[А-Яа-яЁё])',' ','\n'.join(lines))
    report=HERE/'SPEC_FACTORIAL_DIAGNOSTIC_RESULTS.md';report.write_text(text)
    write(root/'report-receipt.json',{'complete':True,'report_sha256':sha(report),'optimizer_updates':0})
    print(json.dumps({'report':str(report),'arms':stats['arms']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args();main(a.root)
