"""Natural-language before/after, independent wording probes and true Q4 exports."""
import argparse
import json
from pathlib import Path
import re
from bf_common import ROOT,HERE,read,write,rows,sha,signature
from bf_spec import install
from ba_report import cluster_difference
from ay_data import op_count

ROLES=['parent_lora','lora','parent_full','full']
LABELS={'parent_lora':'Адаптеры до','lora':'Адаптеры после','parent_full':'Полная3M до','full':'Полная3M после'}

def brief(report):
    result={'primary':report['primary']['summary'],'natural':report['primary']['natural'],'panels':report['primary']['panels'],
        'families':report['primary']['families'],'raw':dict(report['raw']['summary']),'self':dict(report['self']['summary']),
        'navigation':{k:v for k,v in report['navigation'].items()if k!='records'},
        'pool_views':{k:v['summary']for k,v in report['pool_views'].items()},
        'short_regressions':[{'task':r['task'],'passed':r['passed']}for r in report['short_regressions']]}
    for panel in ['raw','self']:
        s=result[panel];s['false_DONE_fraction']=s['false_DONE']/s['DONE']if s['DONE']else None
        s['correct_code_UNSURE']=sum(r['abstained']and r['program_correct']for r in report[panel]['records'])
    return result

def main(root):
    install();assert read(root/'complete.json')['complete']and read(root/'native-verification.json')['complete']
    assert read(root/'postflight.json')['all_frozen_files_verified']and not read(root/'postflight.json')['own_containers_running']
    reports={a:read(root/a/'closed.json')for a in ROLES};selection=read(root/'preselected.json')
    goals={g['id']:g for g in rows(root/'closed-clean.jsonl')}
    assert not selection['closed_used_for_selection']
    stats={'optimizer_updates':12000,'selection':selection,'data':read(root/'teacher-frozen.json'),
        'models':{a:brief(v)for a,v in reports.items()},'paired':{},'training':{a:read(root/a/'training.json')for a in ['lora','full']},
        'native':read(root/'native-verification.json'),
        'development_curves':{a:[{'step':s,'summary':brief(read(root/a/f'development-{s}.json'))}for s in [1000,3000,6000]]for a in ['lora','full']}}
    assert stats['training']['lora']['draw_digest']==stats['training']['full']['draw_digest']
    contrasts=[('parent_lora','lora'),('parent_full','full'),('lora','full')]
    for a,b in contrasts:
        values={}
        for panel in ['natural','generated','editorial','structured']:
            keep=lambda r: r['panel']!='structured'if panel=='natural'else r['panel']in ['known','novel']if panel=='generated'else r['panel']==panel
            x=[r for r in reports[a]['primary']['records']if keep(r)];y=[r for r in reports[b]['primary']['records']if keep(r)]
            values[panel]=cluster_difference(x,y,lambda r:r['program_correct'])
            if panel=='editorial':
                with_template=lambda records:[{**r,'template_id':goals[r['id']]['editorial_template']}for r in records]
                values['editorial_template_clustered']=cluster_difference(with_template(x),with_template(y),lambda r:r['program_correct'],'template_id')
        for panel in ['raw','self']:
            values[panel+'_success']=cluster_difference(reports[a][panel]['records'],reports[b][panel]['records'],lambda r:r['pass'],'task_id')
            values[panel+'_false_DONE']=cluster_difference(reports[a][panel]['records'],reports[b][panel]['records'],lambda r:r['finished']and not r['program_correct'],'task_id')
        stats['paired'][a+'->'+b]=values
    teacher=stats['data'];training=rows(root/'train-clean.jsonl');natural_train=[g for g in training if g['style']=='natural']
    examples=[{'before':g['original_wording'],'after':g['task'],'source':g['wording_source'],'spec':g['spec']}for g in natural_train if g['point_edited']][:12]
    preserved=[{'task':g['task'],'spec':g['spec']}for g in natural_train if g['wording_source']=='old'and not g['point_edited']][:8]
    write(root/'point-edit-examples.json',{'edited':examples,'preserved':preserved})
    quality={}
    for split in ['train','development','closed']:
        values=rows(root/(split+'-clean.jsonl'))
        leaks=[{'id':g['id'],'task':g['task'],'original':g.get('original_wording')}for g in values if re.search(r'\b(?:JSON|items|AST)\b',g['task'],re.I)]
        quality[split]={'total':len(values),'metadata_fragments':len(leaks),'rows':leaks}
    stats['posttraining_data_quality_audit']=quality;write(root/'data-quality-audit.json',quality)
    # A stricter syntactic diagnostic is supplementary; mathematical aliases remain valid.
    structural={}
    for a,v in reports.items():
        natural=[r for r in v['primary']['records']if r['panel']!='structured']
        structural[a]={'total':len(natural),'canonical_AST_equal':sum(r['declared_spec']is not None and signature(r['declared_spec'])==signature(goals[r['id']]['spec'])for r in natural)}
    stats['supplementary_structural_audit']=structural
    diagnostics={};changes={}
    for a,v in reports.items():
        failures=[r for r in v['primary']['records']if r['panel']!='structured'and not r['program_correct']]
        selected=[]
        for panel in ['known','novel','editorial']:
            selected.extend([r for r in failures if r['panel']==panel][:4])
        diagnostics[a]=[{'id':r['id'],'panel':r['panel'],'task':r['task'],'required_spec':goals[r['id']]['spec'],
            'declared_spec':r['declared_spec'],'codec_error':r['codec_error'],'task_audit':r['task_audit'],
            'own_spec_consistency':r['own_spec_consistency']}for r in selected]
    for a,b in contrasts[:2]:
        before={r['id']:r for r in reports[a]['primary']['records']};after={r['id']:r for r in reports[b]['primary']['records']}
        changes[a+'->'+b]={}
        for panel in ['natural','editorial','structured']:
            keys=[k for k,r in before.items()if(r['panel']!='structured'if panel=='natural'else r['panel']==panel)]
            changes[a+'->'+b][panel]={
                'both_correct':sum(before[k]['program_correct']and after[k]['program_correct']for k in keys),
                'gained':sum(not before[k]['program_correct']and after[k]['program_correct']for k in keys),
                'lost':sum(before[k]['program_correct']and not after[k]['program_correct']for k in keys),
                'both_wrong':sum(not before[k]['program_correct']and not after[k]['program_correct']for k in keys)}
    stats['paired_outcomes']=changes
    counts={key:op_count(g['spec']['X'])for key,g in goals.items()}
    stats['natural_by_operations']={}
    for label,predicate in [('0–1',lambda n:n<=1),('2',lambda n:n==2),('3',lambda n:n==3),('4+',lambda n:n>=4)]:
        stats['natural_by_operations'][label]={}
        for role,report in reports.items():
            subset=[r for r in report['primary']['records']if r['panel']!='structured'and predicate(counts[r['id']])]
            stats['natural_by_operations'][label][role]={'passed':sum(r['program_correct']for r in subset),'total':len(subset)}
    write(root/'error-examples.json',diagnostics);write(root/'comparison.json',stats)
    frac=lambda v:f'{v["passed"]}/{v["total"]}'
    lines=['# SPEC Q4: разнообразный естественный русский, адаптеры и полная3M','',
        'Обе ветки продолжены от своих выбранных весов предыдущего очищенного курса, каждая ещё '
        'на6000 обновлений. Родители отличаются, поэтому основное сравнение — до/после для '
        'каждой ветки на одном новом тесте. Финальная разница между ветками отражает всю историю '
        'обучения, а не только причинный эффект последнего способа адаптации.', '',
        '## Новый закрытый Q4-тест','',
        '| Метрика | Адаптеры до | Адаптеры после | Полная3M до | Полная3M после |','|---|---:|---:|---:|---:|']
    lines.append('| Обычный русский, всего | '+' | '.join(frac(stats['models'][a]['natural'])for a in ROLES)+' |')
    for panel in ['known','novel','editorial','structured']:
        lines.append('| '+panel+' | '+' | '.join(frac(stats['models'][a]['panels'][panel])for a in ROLES)+' |')
    lines += ['', 'known/novel — разнообразные естественные формулировки DeepSeek, проверенные отдельно '
        'без целевого AST. editorial — новые заранее написанные шаблоны Codex, не передававшиеся '
        'генератору обучения. Это отдельный стиль, но не независимая человеческая разметка. '
        'У editorial общие40 шаблонов для development и closed с новыми числами и AST: эта '
        'панель проверяет перенос на стиль вне обучения, но не на невиданные после development шаблоны. '
        'structured оценивает сохранение ранее освоенного явного формата и не входит в основную '
        'метрику обычного русского.', '',
        'Для всех четырёх моделей идентичны условия, входы, таблицы, ROM и допуск. Одна попытка '
        'WRITE оценивается по реальному исполнению с сохранением неназванной памяти. Языковой '
        'parser предыдущего курса в этой оценке не используется.', '',
        '| Число операций в условии, обычный русский | Адаптеры до | Адаптеры после | Полная3M до | Полная3M после |',
        '|---|---:|---:|---:|---:|']
    for label,values in stats['natural_by_operations'].items():
        lines.append('| '+label+' | '+' | '.join(frac(values[a])for a in ROLES)+' |')
    lines += ['', 'Это дополнительный срез уже выполненного экзамена по числу узлов операций '
        'в целевой формуле, без числовых листьев и адреса записи. Он не использовался для выбора весов.', '',
        '## Отладка на естественных условиях','',
        '| Режим / модель | Правильный DONE | Все DONE | Ложный DONE | Ошибок среди DONE | Верный код с UNSURE | Незавершено | Переполнения контекста |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for panel in ['raw','self']:
        for a in ROLES:
            s=stats['models'][a][panel];rate='—'if s['false_DONE_fraction']is None else f'{100*s["false_DONE_fraction"]:.1f}%'
            lines.append(f'| {panel} / {LABELS[a]} | {frac(s)} | {s["DONE"]} | {s["false_DONE"]} | {rate} | {s["correct_code_UNSURE"]} | {s["exhausted"]} | {s["context_overflows"]} |')
    lines += ['', 'На каждую модель64 естественных условия × правильный/неверный старт. Это128 '
        'эпизодов, сгруппированных по64 условиям. Успех требует верного кода, актуальных RUN '
        'обоих публичных случаев и принятого DONE. self по-прежнему сверяет код с собственной '
        'первоначальной гипотезой; подтверждение смысла исходного запроса не гарантируется. '
        'В инструментальную выборку входят known/novel, editorial здесь оценивается одним WRITE.', '',
        '| Модель, self | Верный старт завершён /64 | Верный старт испорчен /64 | Ошибочный старт исправлен и завершён /64 |',
        '|---|---:|---:|---:|']
    for a in ROLES:
        s=stats['models'][a]['self']
        lines.append(f'| {LABELS[a]} | {s["correct_starts_completed"]} | {s["correct_starts_corrupted"]} | {s["wrong_starts_repaired"]} |')
    lines += ['', 'Большее число успешных исправлений не отменяет регрессию сохранения уже верной '
        'программы: оба показателя оцениваются отдельно. Выбранный на development профиль '
        'не переназначался по этим закрытым результатам.', '',
        '## Перестановки таблицы констант','',
        '| Представление тех же условий | Адаптеры до | Адаптеры после | Полная3M до | Полная3M после |',
        '|---|---:|---:|---:|---:|']
    for mode in ['extras','full','distractors']:
        lines.append('| '+mode+' | '+' | '.join(frac(stats['models'][a]['pool_views'][mode])for a in ROLES)+' |')
    lines += ['', 'Это повторные представления128 условий, а не новые независимые задачи. '
        'extras переставляет дополнительные литералы, full перемешивает всю таблицу, distractors '
        'добавляет и переставляет отвлекающие константы.', '',
        '## Как подготовлены формулировки','',
        'Старые естественные вопросы сначала проверялись без исходной формулы. Вопросы, признанные проверяющим ясными и точными, '
        'сохранены дословно. Для ошибочного или неоднозначного места запрашивалась минимальная '
        'правка с сохранением стиля; требовалось не менее60% символьного сходства с оригиналом. '
        'После правки условие снова проверялось без эталона. Новые варианты использовали разные '
        'обычные способы постановки задачи, а не фиксированную скобочную грамматику.', '',
        'Слепые запросы содержали только вопрос, режим углов и непрозрачный ID. Варианты одного '
        'выражения никогда не подавались проверяющему вместе. Восстановленная формула сравнивалась '
        'с целевой по операциям, литералам, порядку аргументов и записи памяти с заранее заданными '
        'алиасами reciprocal/1/x, square/x^2 и pow10/10^x. Близость очень малых чисел для принятия '
        'формулировки не использовалась.', '',
        'Дополнительно отмечались конкретные риски: неявная граница аргумента функции перед '
        '«плюс/умножить/разделить», неясное присоединение «возведённое в степень» и смешение '
        'основания с показателем. Эти проверки только вызывали локальную правку и не выбирали '
        'ответ за модель. Для сгенерированных development/closed использовались два отдельных '
        'слепых запроса. Учитель один и тот же DeepSeek-V4.1-Flash: это уменьшает часть ошибок '
        'разметки, но не является независимой проверкой другим человеком или другой моделью. '
        'При просмотре найдена и избыточная правка: к уже явному «Результат запиши в R8» '
        'добавлено «Результат X запиши в R8», поскольку слепой проверяющий сначала пропустил '
        'запись в память. Смысл принятого примера сохранён, но не каждая правка означает '
        'настоящую неоднозначность исходной фразы. После фиксации корпуса этот пример не '
        'переразмечался; отдельная editorial-панель ограничивает зависимость оценки от учителя.', '',
        '| Набор | AST | Вопросов | Старые сохранены | Старые точечно исправлены | Новые точечно исправлены |',
        '|---|---:|---:|---:|---:|---:|']
    for split,c in teacher['counts'].items():
        lines.append(f'| {split} | {c["trees"]} | {c["questions"]} | {c["original_kept_exactly"]} | {c["old_point_edited"]} | {c["new_point_edited"]} |')
    for e in examples[:4]:lines += ['', 'Было: '+e['before'],'','Стало: '+e['after']]
    lines += ['', f'Финальный аудит нашёл служебные фрагменты JSON/items/AST в {quality["train"]["metadata_fragments"]} '
        f'из {quality["train"]["total"]} учебных вопросов; development: {quality["development"]["metadata_fragments"]}, '
        f'closed: {quality["closed"]["metadata_fragments"]}. Например, «Только JSON items» ошибочно попало '
        'в текст вопроса при правке учителем. Это пропуск фильтра подготовки корпуса, а не полезное уточнение. '
        'Веса, зафиксированный корпус и оценки после открытия closed не менялись. Такие строки следует '
        'исправить или исключить перед следующим обучением; они перечислены в data-quality-audit.json. '
        'Этот аудит проверяет конкретные служебные маркеры и не доказывает отсутствие всех ошибок разметки.']
    lines += ['', 'Полные примеры: point-edit-examples.json. Тексты и результаты проверок сохранены '
        'в teacher-audit.jsonl; точные HTTP-параметры и ответы — в локальном teacher-cache. '
        'Эталонные программы проверены ROM при подготовке AST; затем для каждого принятого '
        'вопроса подтверждено побайтовое сохранение машинной программы при пересборке таблицы.', '',
        '## Обучение и защита теста','',
        'В пакете32 примера:24 естественных перевода,4 повтора явного формата и4 инструментальных '
        'состояния. Среди естественных чаще выбирались сохранённые исходные и точечно исправленные '
        'условия. Переводы подаются парами с разным порядком таблицы констант. На них обучается '
        'тело SPEC, а классификатор действий — на инструментальных состояниях. Положительные '
        'DONE и исправления получены новыми реальными сессиями с обновлённым проверяющим.', '',
        'У обеих веток совпали все выборки и их digest. Продолжались318208 коэффициентов адаптеров '
        'или все3022080 весов. Q4 используется при каждом проходе; вычисления и KV FP32, '
        'контекст1024. LR адаптеров1e-4; полных весов2e-5, их эмбеддингов1e-5; AdamW, разогрев100 '
        'шагов и одинаковый косинусный график. Нового критика, DPO и штрафа DONE нет.', '',
        'Новый development/closed исключает нормализованные сигнатуры прежних пяти семантических '
        'раундов и всего текущего обучения, включая инструментальные повторы. Удержаны новые '
        'числовые литералы и цепочки трёх операций. Ранее открытые BE development/closed явно '
        'сняты с роли теста и могли войти в новое обучение. Все вопросы, правила и исходники обучения и экзамена '
        'зафиксированы до SGD; ученик не генерировал ответы нового closed до фиксации обоих выборов.', '',
        'Чекпойнты1000/3000/6000 выбирались только на новом development. Сначала сохраняются '
        'известные пробы синуса и качество structured/editorial в пределах5п.п. от своего родителя. '
        'Затем максимизируется точность естественных вопросов, худшая естественная панель, '
        'ошибки формата и показатели отладки. Исходный шаг0 включён как допустимый вариант.', '',
        f'Выбраны шаги: lora={selection["branches"]["lora"]["step"]}, full={selection["branches"]["full"]["step"]}. '
        f'Предпочтительная ветка до closed: {selection["preferred"]}. Итоги closed не меняли веса или правило.', '',
        '| Шаг development | Адаптеры: русский | Полная3M: русский | Адаптеры: editorial | Полная3M: editorial | Адаптеры: self успех / ложный DONE | Полная3M: self успех / ложный DONE |',
        '|---:|---:|---:|---:|---:|---:|---:|']
    for i,step in enumerate([1000,3000,6000]):
        l,f=[stats['development_curves'][a][i]['summary']for a in ['lora','full']]
        lines.append(f'| {step} | {frac(l["natural"])} | {frac(f["natural"])} | {frac(l["panels"]["editorial"])} | {frac(f["panels"]["editorial"])} | {frac(l["self"])} / {l["self"]["false_DONE"]} | {frac(f["self"])} / {f["self"]["false_DONE"]} |')
    lines += ['', 'Разные навыки менялись не синхронно. Выбор прежде всего оптимизирует перевод '
        'обычного русского при сохранении заданных навыков; более поздний чекпойнт может '
        'лучше переводить условия и одновременно хуже завершать инструментальный цикл. '
        'Промежуточные веса не переоценивались на closed после просмотра его результатов.', '',
        '## Уточнённая численная проверка','',
        'Для ненулевого эталона применяется относительный допуск2e-6, для точного нуля — '
        'абсолютный1e-12. Так18.25^(-70) и70^(-70) не становятся эквивалентными из-за малого '
        'масштаба. Исправлен эталон sign(0)=0 согласно фактическому ROM. Изменения действуют '
        'только в этом изолированном раунде и одинаково применены к обоим родителям и ученикам. '
        'Поэтому абсолютные проценты старого и нового экзаменов напрямую не сопоставляются.', '',
        '## Парная оценка','', '| Сравнение | Панель | Разность, п.п. | 95% bootstrap |','|---|---|---:|---:|']
    for label,values in stats['paired'].items():
        for panel,v in values.items():
            lo,hi=v['bootstrap_95'];lines.append(f'| {label} | {panel} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} |')
    lines += ['', 'Bootstrap группирует повторные старты по условию. editorial_template_clustered '
        'дополнительно группирует числовые варианты по общему шаблону, чтобы не считать четыре '
        'варианта одной фразы четырьмя независимыми стилями. Здесь разность усредняется по шаблонам. Каждый способ имеет один '
        'запуск обучения; интервалы по задачам не оценивают разброс обучения между сидами.', '',
        '| Продолжение | Панель | Стало верно | Стало неверно |',
        '|---|---|---:|---:|']
    for label,values in changes.items():
        for panel,v in values.items():lines.append(f'| {label} | {panel} | {v["gained"]} | {v["lost"]} |')
    lines += ['', 'Примеры оставшихся ошибок с запросом, целевой и полученной SPEC и контрпримером '
        'исполнения сохранены в error-examples.json. Это диагностика после закрытого экзамена; '
        'она не использовалась для выбора весов или изменения данного курса.', '',
        '## Экспорт и ограничения','', '| Профиль | MKA, байт | Нативных проб |','|---|---:|---:|']
    for a,v in stats['native']['models'].items():lines.append(f'| {a} | {v["mka_bytes"]} | {v["probes"]} |')
    lines += ['', 'Проверены настоящий Q4-переэкспорт, неизменность ID русского словаря и потоков '
        'B200/CPU/C++ на выбранных пробах. Родительские MKA сохранены побайтово, у адаптеров '
        'подтверждены ограничения на замороженные веса. Оба ученика остаются моделями3022080 '
        'параметров с прежним SPEC-кодеком и шестью действиями.', '',
        'Поддерживаются прямолинейная арифметика и необязательная запись одного результата. '
        'Ветвления и циклы не входят в этот экзамен. Это конечные проверки на ограниченной '
        'области, не доказательство корректности произвольного русского запроса. Основной '
        'профиль и прошивка не заменены; физических замеров PicoCalc нет. Все собственные '
        'учебные и оценочные процессы завершены.', '',
        f'Артефакты: {root}; comparison.json; четыре профиля в export/{{parent_lora,lora,parent_full,full}}. '
        'Выбранные продолжаемые веса: {lora,full}/best.safetensors.', '']
    text=re.sub(r'(?<=[А-Яа-яЁё])(?=\d)|(?<=\d)(?=[А-Яа-яЁё])',' ','\n'.join(lines))
    report=HERE/'NATURAL_SPEC_LORA_FULL_RESULTS.md';report.write_text(text)
    write(root/'report-receipt.json',{'report_sha256':sha(report),'optimizer_updates':12000,'closed_used_for_selection':False})
    print(json.dumps({'report':str(report),'models':stats['models'],'selection':selection},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args();main(a.root)
