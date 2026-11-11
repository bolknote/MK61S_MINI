"""Closed Q4 comparison of clean-condition LoRA and complete3M training."""
import argparse
import collections
import json
from pathlib import Path
import re
from be_common import ROOT,HERE,PARENT,read,write,rows,sha
from ba_report import cluster_difference

def summary(report):
    out={k:report[k]['summary']for k in ['primary','raw','self']}
    out['panels']=report['primary']['panels'];out['families']=report['primary']['families'];out['styles']=report['primary']['styles']
    out['pool_views']={k:v['summary']for k,v in report['pool_views'].items()}
    out['navigation']={k:v for k,v in report['navigation'].items()if k!='records'}
    out['short_regressions']=[{k:r[k]for k in ['task','passed']}for r in report['short_regressions']]
    intent={r['id']:r['intent']['tested_equal']for r in report['primary']['records']}
    for gate in ['raw','self']:
        records=report[gate]['records'];s=out[gate]=dict(out[gate])
        s['false_DONE_fraction']=s['false_DONE']/s['DONE']if s['DONE']else None
        s['false_DONE_with_wrong_initial_intent']=sum(r['finished']and not r['program_correct']and not intent[r['task_id']]for r in records)
        s['correct_code_UNSURE']=sum(r['program_correct']and r['abstained']for r in records)
    return out

def main(root):
    assert read(root/'complete.json')['complete']and read(root/'native-verification.json')['complete']
    assert read(root/'postflight.json')['all_frozen_files_verified']and not read(root/'postflight.json')['own_containers_running']
    reports={a:read(root/a/'closed.json')for a in ['parent','lora','full']};selection=read(root/'preselected.json')
    assert not selection['closed_used_for_selection']
    stats={'optimizer_updates':8000,'selected':selection,'data':read(root/'data-frozen.json'),
        'models':{a:summary(v)for a,v in reports.items()},'training':{a:read(root/a/'training.json')for a in ['lora','full']},
        'paired':{},'native':read(root/'native-verification.json'),'extended_holdout_audit':read(root/'extended-holdout-audit.json'),
        'semantic_audit':read(root/'semantic-audit.json'),
        'development_curves':{a:[{'step':step,'summary':summary(read(root/a/f'development-{step}.json'))}for step in [1000,2500,4000]]for a in ['lora','full']}}
    assert stats['training']['lora']['draw_digest']==stats['training']['full']['draw_digest']
    for a,b in [('parent','lora'),('parent','full'),('lora','full')]:
        panels={}
        for panel in ['all','core','editorial']:
            filt=lambda r:panel=='all'or(r['panel']=='editorial'if panel=='editorial'else r['panel']!='editorial')
            x=[r for r in reports[a]['primary']['records']if filt(r)];y=[r for r in reports[b]['primary']['records']if filt(r)]
            panels[panel]=cluster_difference(x,y,lambda r:r['program_correct'])
        panels['self_success']=cluster_difference(reports[a]['self']['records'],reports[b]['self']['records'],lambda r:r['pass'],'task_id')
        panels['self_false_DONE']=cluster_difference(reports[a]['self']['records'],reports[b]['self']['records'],lambda r:r['finished']and not r['program_correct'],'task_id')
        stats['paired'][a+'->'+b]=panels
    write(root/'comparison.json',stats)
    # Record how the previously flagged conditions were actually replaced.
    audit_path=ROOT.parent/'spec-factorial-diagnostic-v1/server-results/language-review.json';cleaning=[]
    if audit_path.exists():
        training=rows(root/'train-clean.jsonl')
        for old in read(audit_path)['flags']:
            samples=[g for g in training if g.get('source_id')==old['id']]
            assert samples,old['id']
            cleaning.append({'source_id':old['id'],'old_question':old['task'],'new_questions':[g['task']for g in samples],
                'AST_preserved':True,'roundtrip_parser_verified':all(g['scope_roundtrip_verified']for g in samples)})
        write(root/'cleanup-examples.json',cleaning)
    names=['parent','lora','full'];labels={'parent':'Исходная SPEC','lora':'Адаптеры','full':'Полная3M'}
    lines=['# SPEC Q4: очищенные формулировки, адаптеры и полное дообучение','',
        'Выполнены два параллельных продолжения по4000 обновлений на двух B200. '
        'Обе ветки начали с одного и того же выбранного SPEC-чекпойнта: исходные FP32 master-веса '
        'и Q4 payload на B200 совпали точно. Во время обучения каждый прямой проход использовал Q4 '
        'с FP32 вычислениями. После обучения каждый кандидат заново упакован и оценён именно в Q4.', '',
        'Все результаты до/после ниже относятся к одному новому закрытому тесту. Его AST, вопросы, '
        'политику выбора и исходники зафиксировали до градиентных обновлений. Для каждой ветки выбран '
        'один чекпойнт по development, затем оба выбора зафиксированы перед открытием closed. '
        'Исходный чекпойнт включён как шаг0.', '',
        '## Новый закрытый тест','', '| Метрика | Исходная SPEC | Адаптеры | Полная3M |','|---|---:|---:|---:|']
    frac=lambda v:f'{v["passed"]}/{v["total"]}'
    lines.append('| Правильная программа за одну WRITE | '+' | '.join(frac(stats['models'][a]['primary'])for a in names)+' |')
    for panel in ['known','novel','editorial']:
        lines.append('| '+panel+' | '+' | '.join(frac(stats['models'][a]['panels'][panel])for a in names)+' |')
    for family in ['constant','numeric','register','composition']:
        lines.append('| '+family+' | '+' | '.join(frac(stats['models'][a]['families'][family])for a in names)+' |')
    difference=stats['paired']['lora->full']['all'];lo,hi=difference['bootstrap_95']
    lines += ['', f'Разность полной ветки и адаптеров: {100*difference["difference"]:+.2f}п.п.; '
        f'95% парный интервал {100*lo:+.2f} … {100*hi:+.2f}п.п. '
        'Убедительное преимущество полного дообучения на этом тесте не установлено.', '',
        'Основной выигрыш получен на условиях с явными границами аргументов. На обычных '
        'редакторских запросах исходная модель решила '
        f'{frac(stats["models"]["parent"]["panels"]["editorial"])}, адаптеры — '
        f'{frac(stats["models"]["lora"]["panels"]["editorial"])}, полная ветка — '
        f'{frac(stats["models"]["full"]["panels"]["editorial"])}. '
        'Следовательно, общий рост основной метрики не подтверждает улучшение свободного '
        'русского ввода. На этой панели обе обученные версии набрали меньше исходной; '
        'размер и неопределённость изменения приведены отдельно в парной оценке.', '']
    lines += ['', 'known и novel состоят из выражений с явными границами аргументов. В novel отдельно '
        'удержаны новые числовые литералы и цепочки трёх операций. editorial —80 обычных русских '
        'заданий по заранее написанным редакторским шаблонам Codex; таких шаблонов нет в обучении. '
        'Это не независимая человеческая разметка и не исчерпывающая проверка свободного русского языка.', '',
        'Основной тест принудительно запрашивает WRITE, затем SPEC компилируется прежним детерминированным '
        'компилятором и проверяется ROM на отдельных аудиторских входах. Все неназванные регистры '
        'должны сохраниться. Parser очистки не используется при ответе модели или оценке её предсказания.', '',
        '## Отладка и DONE','', '| Режим / модель | Правильно завершено | Принято DONE | Ложных DONE | Ошибок среди DONE | Верный код с UNSURE |','|---|---:|---:|---:|---:|---:|']
    for gate in ['raw','self']:
        for a in names:
            s=stats['models'][a][gate];rate='—'if s['false_DONE_fraction']is None else f'{100*s["false_DONE_fraction"]:.1f}%'
            lines.append(f'| {gate} / {labels[a]} | {frac(s)} | {s["DONE"]} | {s["false_DONE"]} | {rate} | {s["correct_code_UNSURE"]} |')
    lines += ['', 'Для каждой модели используются те же64 условия × правильный/неверный старт. '
        'Это128 эпизодов,64 группы для оценки неопределённости. Отладка проверяется на основных '
        'панелях known/novel; editorial здесь оценивается только одношагово. raw оставляет решение о DONE сети; '
        'self проверяет программу по её собственной первоначальной SPEC, а не по эталону запроса. '
        'Неподтверждённая формула по-прежнему может дать ложный DONE. Правильный код с UNSURE не считается успехом.', '',
        '## Сохранение навыков и таблицы констант','', '| Проверка | Исходная SPEC | Адаптеры | Полная3M |','|---|---:|---:|---:|']
    for mode in ['extras','full','distractors']:
        lines.append('| Таблица '+mode+' | '+' | '.join(frac(stats['models'][a]['pool_views'][mode])for a in names)+' |')
    for i,r in enumerate(stats['models']['parent']['short_regressions']):
        lines.append('| '+r['task']+' | '+' | '.join(str(stats['models'][a]['short_regressions'][i]['passed'])for a in names)+' |')
    lines.append('| RUN → DONE | '+' | '.join(f'{stats["models"][a]["navigation"]["cycle_pass"]}/{stats["models"][a]["navigation"]["total"]}'for a in names)+' |')
    lines += ['', 'Перестановки проверяют те же числовые задачи и не увеличивают число независимых условий. '
        'Реальные программы при перестановке индексов сохраняются побайтово. Полное дообучение '
        'сохраняет токенизатор и словарь, но может менять эмбеддинги и нормализации; адаптеры сохраняют '
        'входные эмбеддинги. Эти ограничения проверены раздельно при экспорте.', '',
        '## Что очищено','',
        f'Переформулированы {stats["data"]["cleaned_old_ASTs"]} ранее открытых выражений, '
        'включая прежние ошибки и снятые с роли теста development/closed. Новые учебные деревья '
        'добавлены отдельно. Старые свободные формулировки не копировались ни в перевод, ни в '
        'инструментальные повторы: условия заново построены по целевой SPEC.', '',
        'У каждого аргумента сложной операции явно обозначены границы. Используются русские '
        'названия операций, скобочные выражения, именные конструкции и последовательные инструкции '
        'с явно указанным «полученным результатом». Отдельный рекурсивный parser восстановил AST '
        'и адрес записи из каждой контролируемой формулировки. Проверка требовала точного совпадения '
        'дерева, литералов, порядка аргументов и назначения памяти. Новых вызовов большого учителя нет; '
        'использованы прежние проверенные AST и новые ROM-проверенные выражения.', '',
        '| Набор | Выражений | Формулировок |','|---|---:|---:|']
    for split,count in stats['data']['counts'].items():lines.append(f'| {split} | {count["trees"]} | {count["questions"]} |')
    for example in cleaning[:2]:
        lines += ['', 'Было: '+example['old_question'],'','Стало: '+example['new_questions'][0]]
    lines += ['', 'Полный разбор шести ранее отмеченных условий: cleanup-examples.json. '
        'Новая закрытая часть исключает сигнатуры всех сохранённых train/development/closed '
        'четырёх предыдущих семантических раундов и текущего train; учитываются коммутативность '
        '+/* и несущественный режим углов. Не проверяются все алгебраические тождества и всё '
        'предобучение исходной Flourish. Дополнительно проверены все17702 учебных состояния, '
        'включая инструментальные повторы: ноль пересечений целевых AST с новым development/closed, '
        'ноль удержанных троек операций и ноль новых тестовых чисел в учебных таблицах констант. '
        'Результат: extended-holdout-audit.json.', '',
        '## Одинаковое обучение и выбор','', '| Параметр | Адаптеры | Полная3M |','|---|---:|---:|',
        '| Обновляемых коэффициентов | 318208 | 3022080 |','| Обновлений | 4000 | 4000 |',
        '| Пакет | 32 | 32 |','| Контекст | 1024 | 1024 |']
    lines.append('| Выбранный шаг | '+' | '.join(str(selection['branches'][a]['step'])for a in ['lora','full'])+' |')
    lines += ['', 'В каждом пакете28 примеров перевода, подаваемых парами с разным порядком таблицы '
        'констант, и4 инструментальных повтора: RUN00/01 поровну, DONE, исправление и UNSURE. '
        'Первые400 шагов используют простые выражения. На переводах оптимизируется тело SPEC; '
        'классификатор действий обучается на инструментальных повторах, чтобы частый WRITE '
        'на пустом состоянии не подавлял другие действия. Digest всех выборок и счётчики '
        'совпали у двух веток.', '',
        'Для адаптеров LR1e-4, для полного дообучения3e-5, для полных входных эмбеддингов1.5e-5; '
        'AdamW, разогрев100 шагов и общий косинусный график. Q4 forward согласован с экспортом; '
        'нормализации и вычисления FP32. Различие LR зафиксировано до SGD, дополнительные '
        'поиски гиперпараметров по closed не проводились.', '',
        'Выбор сначала сохраняет три известные пробы синуса, затем максимизирует среднее '
        'точности основной и редакторской панелей development с равными весами. Далее '
        'учитываются худшая панель, общее число решений, ошибки формата, raw-успех и self-ошибки. '
        'В development редакторских задач32; выводы о малых различиях на этой панели ограничены размером выборки.', '',
        f'Предпочтительная ветка до открытия closed: **{selection["preferred"]}**. '
        'Результаты closed не меняли этот выбор. Обе выбранные ветки и исходная модель '
        'проверены на новом тесте полностью.', '',
        '## Парные различия','', '| Сравнение | Панель | Разность, п.п. | 95% bootstrap |','|---|---|---:|---:|']
    for comparison,values in stats['paired'].items():
        for panel,v in values.items():
            lo,hi=v['bootstrap_95'];lines.append(f'| {comparison} | {panel} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} |')
    lines += ['', 'Для отладки повторные старты группируются по условию. Интервалы относятся '
        'к задачам, а не разбросу обучения между сидами: здесь один запуск каждого способа. '
        'Полные кривые development всех трёх контрольных точек сохранены в comparison.json.', '',
        '## Дополнительная проверка семантической метрики','',
        'После экзамена дополнительно сопоставлены деревья с учётом коммутативности и '
        'несущественного углового режима. Это диагностическая метрика: разные деревья '
        'могут задавать одну и ту же функцию. Исходные численные оценки, допуск, выбор '
        'весов и результаты экзамена не менялись.', '',
        '| Модель | Совпало дерево | Численно совпало, дерево отличается |','|---|---:|---:|']
    for a,v in stats['semantic_audit']['models'].items():
        lines.append(f'| {a} | {v["AST_equal_up_to_commutativity_and_irrelevant_angle"]}/{v["total"]} | {v["numerically_equal_but_different_AST"]} |')
    lines += ['', 'Выявлена особенность прежнего допуска: для очень малых констант абсолютный '
        'порог2e-6 может считать разные значения совпадающими. Например, у полной ветки '
        '18.25^(-70) заменено на70^(-70): численная проверка SPEC сочла значения близкими, '
        'но ROM завершил предсказанную программу ошибкой, и основной тест засчитал отказ. '
        'Это не доказательство правильного понимания и не обнаруженный сбой компилятора. '
        'Для следующего экзамена стоит заранее разделить проверку значащих цифр, '
        'поведение около нуля и точность восстановления условий. Полный разбор: semantic-audit.json.', '',
        '## Экспорт','', '| Версия | MKA, байт | Нативных проб | Изменены входные эмбеддинги |','|---|---:|---:|---:|']
    for a,n in stats['native']['models'].items():lines.append(f'| {a} | {n["mka_bytes"]} | {n["probes"]} | {n["input_embedding_weights_changed"]} |')
    lines += ['', 'Проверены переупаковка настоящего Q4, одинаковые словари токенов, потоков '
        'B200/CPU/C++ на выбранных пробах, сохранение исходной MKA и размеров модели. '
        'Каждый экспорт содержит3022080 параметров. KV и вычисления остаются FP32; '
        'сокращение битности активаций не применялось.', '',
        'Все собственные задачи этого раунда завершены. Протокол инструментов, прошивка '
        'и основной профиль не заменены. Скорость и пиковая память физического PicoCalc '
        'не измерены. Область задач — прямая арифметика и необязательная запись одного '
        'результата; ветвления и циклы этим тестом не покрываются. Конечные численные '
        'проверки с допуском2e-6 не являются доказательством на произвольной области.', '',
        f'Артефакты: {root}; экспорт: export/{{parent,lora,full}}/{{hf,model.mkqb,model.mka}}. '
        'Продолжать обучение можно из {lora,full}/best.safetensors. Основные результаты: '
        '{parent,lora,full}/closed.json и comparison.json.', '']
    text=re.sub(r'(?<=[А-Яа-яЁё])(?=\d)|(?<=\d)(?=[А-Яа-яЁё])',' ','\n'.join(lines))
    report=HERE/'CLEAN_SPEC_LORA_FULL_RESULTS.md';report.write_text(text)
    write(root/'report-receipt.json',{'report_sha256':sha(report),'optimizer_updates':8000,'closed_used_for_selection':False})
    print(json.dumps({'report':str(report),'models':stats['models'],'selected':selection},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args();main(a.root)
