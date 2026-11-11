"""Natural-language before/after, independent wording probes and true Q4 exports."""
import argparse
import json
from pathlib import Path
import re
from bh_common import ROOT,HERE,read,write,rows,sha,signature
from bh_spec import install
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
            for label,initial,metric in [('corruption',True,lambda r:not r['program_correct']),('repair',False,lambda r:r['pass'])]:
                x=[r for r in reports[a][panel]['records']if r['initially_correct']==initial];y=[r for r in reports[b][panel]['records']if r['initially_correct']==initial]
                values[panel+'_'+label]=cluster_difference(x,y,metric,'task_id')
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
    tool_examples={}
    for role,v in reports.items():
        tool_examples[role]={}
        for gate in ['raw','self']:
            records=v[gate]['records'];picked=[];seen=set()
            selectors=[('false_DONE',lambda r:r['finished']and not r['program_correct']),('corruption',lambda r:r['initially_correct']and not r['program_correct']),('failed_repair',lambda r:not r['initially_correct']and not r['pass']),('generation_error',lambda r:any(h['kind']=='generation_error'for h in r['history']))]
            for label,predicate in selectors:
                for record in [r for r in records if predicate(r)][:2]:
                    if record['id']in seen:continue
                    seen.add(record['id']);picked.append({'diagnostic':label,'task':goals[record['task_id']]['task'],'record':record})
            tool_examples[role][gate]=picked
    write(root/'tool-error-examples.json',{'posthoc_no_model_changes':True,'models':tool_examples})
    stats['paired_outcomes']=changes
    counts={key:op_count(g['spec']['X'])for key,g in goals.items()}
    stats['natural_by_operations']={}
    for label,predicate in [('0–1',lambda n:n<=1),('2',lambda n:n==2),('3',lambda n:n==3),('4+',lambda n:n>=4)]:
        stats['natural_by_operations'][label]={}
        for role,report in reports.items():
            subset=[r for r in report['primary']['records']if r['panel']!='structured'and predicate(counts[r['id']])]
            stats['natural_by_operations'][label][role]={'passed':sum(r['program_correct']for r in subset),'total':len(subset)}
    fixed={}
    for arm in ['lora','full']:
        f=root/('fixed6000_'+arm)/'closed.json'
        if(ROOT/'fixed-audit-complete.json').exists()and f.exists():fixed[arm]=read(f)
    stats['fixed6000_models']={a:brief(v)for a,v in fixed.items()}
    stats['fixed6000_not_used_for_selection']=True
    stats['fixed6000_paired']={}
    for arm,v in fixed.items():
        values={}
        for gate in ['raw','self']:
            a=reports['parent_'+arm][gate]['records'];b=v[gate]['records']
            values[gate+'_false_DONE']=cluster_difference(a,b,lambda r:r['finished']and not r['program_correct'],'task_id')
            for label,initial,metric in [('corruption',True,lambda r:not r['program_correct']),('repair',False,lambda r:r['pass'])]:
                values[gate+'_'+label]=cluster_difference([r for r in a if r['initially_correct']==initial],[r for r in b if r['initially_correct']==initial],metric,'task_id')
        stats['fixed6000_paired'][arm]=values
    write(root/'error-examples.json',diagnostics);write(root/'comparison.json',stats)
    frac=lambda v:f'{v["passed"]}/{v["total"]}'
    lines=['# Парные контрпримеры: адаптеры и полная 3M в Q4','',
        'Обе ветки обучены по 6000 обновлений от собственных выбранных родителей BF, до неудачного раунда BG. '
        'Веса BG не использовались. Родители различаются; основное сравнение — до/после каждой ветки на одних новых условиях.', '',
        '## Основные показатели закрытого теста','']
    for gate in ['raw','self']:
        lines += ['### '+gate,'','| Метрика | Адаптеры до | Адаптеры после | Полная 3M до | Полная 3M после |','|---|---:|---:|---:|---:|']
        for title,field,denominator in [('Ложные DONE','false_DONE','total'),('Испорчен верный старт','correct_starts_corrupted','correct_starts'),('Успешно исправлен ошибочный старт','wrong_starts_repaired','wrong_starts'),('Все успешные завершения','passed','total'),('UNSURE','abstained','total'),('Исчерпан лимит / ошибка генерации','exhausted','total')]:
            lines.append('| '+title+' | '+' | '.join(f'{stats["models"][role][gate][field]}/{stats["models"][role][gate][denominator]}'for role in ROLES)+' |')
        lines.append('')
    lines += ['raw разрешает модели заявить DONE без механического подтверждения собственной SPEC. '
        'self проверяет программу относительно первоначальной SPEC модели; это не подтверждение смысла русского условия. '
        'Успех требует правильной программы по скрытому эталону, актуальных RUN 00/01 и принятого DONE. '
        'Каждое условие имеет правильный и ошибочный старт; bootstrap группирует их по условию.', '',
        '## Сохранение перевода условий','', '| Панель | Адаптеры до | Адаптеры после | Полная 3M до | Полная 3M после |','|---|---:|---:|---:|---:|']
    lines.append('| Обычный русский | '+' | '.join(frac(stats['models'][a]['natural'])for a in ROLES)+' |')
    for panel in ['known','novel','editorial','structured']:
        lines.append('| '+panel+' | '+' | '.join(frac(stats['models'][a]['panels'][panel])for a in ROLES)+' |')
    lines += ['', 'known/novel — новые формулировки учителя с раздельной слепой проверкой смысла, '
        'без AST в проверяющем запросе. Проверки A/B выполняет одна и та же модель DeepSeek-V4.1-Flash; '
        'это не независимая человеческая разметка. editorial использует прежние шаблоны с новыми числами '
        'и AST: прежние экземпляры могли войти в обучение, поэтому это проверка сохранения языка, '
        'не перенос на невиданный стиль. structured проверяет явный формат. Основная метрика — реальное '
        'ROM-исполнение одной принудительной попытки WRITE, а не полный цикл отладки.', '',
        '## Парный курс и повтор исправлений','',
        'Пакет из 32 примеров: 6 естественных переводов, 2 повтора явного формата, '
        '8 пар правильной и ошибочной программы (16 состояний) и 8 повторов BF: '
        '4 исправления, 2 RUN, 1 DONE, 1 UNSURE. Переводы обучают тело SPEC; инструментальные строки — '
        'действие и тело ответа. Правильные старты больше не дублируются четырежды.', '',
        'В каждой паре совпадают условие, входы, цель и перестановка констант; различаются текущий код '
        'и наблюдения его исполнения. Мутации предпочитают ошибки операции, аргумента и порядка, '
        'сохраняя фактически полученный тип в данных. Ошибочность проверена ROM; последовательность '
        'WRITE исправления → RUN → DONE действительно завершает задачу с правильным результатом. '
        'Корректный старт получает DONE только после проверки фактического принятия harness. '
        'В видимом состоянии нет скрытой SPEC, эталонного кода или скрытых тестов. '
        'Старые исправления берутся из замороженных BF-траекторий с тем же строгим проверяющим.', '',
        'Обе ветки получили одинаковые выборки, подтверждённые draw_digest. Обучались 318208 '
        'параметров адаптеров либо все 3022080 параметров. Q4 используется при каждом проходе, '
        'вычисления и KV FP32, окно 1024. Архитектура, словарь и шесть действий сохранены. '
        'Начальные master-веса и упакованные Q4-веса на B200 точно совпали со своими BF-родителями.', '',
        '## Отбор и защита экзамена','',
        'До SGD заморожены данные, численные правила и код обучения/оценки. Новый development/closed '
        'исключает нормализованные сигнатуры всех предыдущих раундов, включая BG, и текущих учебных '
        'целей. Проверены также новые литералы, их таблицы и отложенные цепочки операций. '
        'Старые уже открытые экзамены могли стать учебными данными, но не сохраняли статус теста.', '',
        'Чекпойнты 0/1000/3000/6000 выбирались только на новом development. '
        'raw и self проверяются раздельно: успешных исправлений не должно стать меньше, '
        'ложных DONE и порчи верного кода — больше. Дополнительно сохраняются короткие пробы '
        'и языковые панели в пределах 5 п.п. от родителя. Среди допустимых вариантов '
        'максимизируется минимум успешных исправлений raw/self, затем суммарные завершения, '
        'затем минимизируются ложные DONE и порча. Родитель остаётся допустимым вариантом. '
        'Компенсировать потерю исправлений уменьшением порчи больше нельзя.', '',
        f'До открытия closed выбраны lora={selection["branches"]["lora"]["step"]}, '
        f'full={selection["branches"]["full"]["step"]}; предпочтительная ветка: {selection["preferred"]}. '
        'Выбор после просмотра closed не менялся. Development использует до 256 условий '
        '(по 128 known/novel, при нехватке — все доступные), closed — 256 условий, '
        'с двумя стартами на каждое.', '',
        '## Парные интервалы','', '| Сравнение | Показатель | Разность, п.п. | 95% bootstrap |','|---|---|---:|---:|']
    for label,values in stats['paired'].items():
        for panel,v in values.items():
            if panel not in ['natural','raw_corruption','raw_repair','raw_false_DONE','self_corruption','self_repair','self_false_DONE','self_success']:continue
            lo,hi=v['bootstrap_95'];lines.append(f'| {label} | {panel} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} |')
    lines += ['', 'Положительная разность для corruption и false_DONE означает ухудшение; '
        'для repair и success — улучшение. Это интервалы по условиям для одного запуска каждого '
        'способа, не оценка разброса между сидами обучения.', '',
        '## Экспорты и ограничения','', '| Профиль | MKA, байт | Совпавших проб B200/CPU/C++ |','|---|---:|---:|']
    for role,v in stats['native']['models'].items():lines.append(f'| {role} | {v["mka_bytes"]} | {v["probes"]} |')
    lines += ['', 'Проверены реальный Q4-переэкспорт и ID русского словаря; родительские MKA '
        'сохранены побайтово. Основные учебные и оценочные контейнеры завершены; основной профиль и прошивка '
        'не заменены. Физических измерений PicoCalc нет. Область экзамена — прямолинейная '
        'арифметика и запись результата, без ветвлений и циклов. Конечные тесты не доказывают '
        'корректность произвольного русского запроса.', '',
        'Примеры оставшихся ошибок: error-examples.json; полные ошибочные инструментальные траектории: tool-error-examples.json. Полные метрики, development-кривые, '
        'перестановки констант и интервалы: comparison.json. Аудит служебных маркеров: data-quality-audit.json.', '',
        f'Артефакты: {root}; выбранные веса {{lora,full}}/best.safetensors; '
        'четыре Q4-профиля export/{parent_lora,lora,parent_full,full}.', '']
    if len(fixed)==2:
        lead=['## Итог фактического дообучения, фиксированный шаг 6000','',
            'Ни один обученный чекпойнт не прошёл все ограничения development, поэтому основной отбор сохранил обоих родителей BF. Чтобы не выдавать сравнение одинаковых родительских весов за эффект обучения, ниже отдельно показана заранее объявленная проверка фактически обученных финальных весов 6000. Эта проверка не меняла выбор.', '',
            '| Метрика self, до → после | Адаптеры | Полная 3M |','|---|---:|---:|']
        for label,field,den in [('Ложные DONE','false_DONE','total'),('Испорчен верный старт','correct_starts_corrupted','correct_starts'),('Успешно исправлен ошибочный старт','wrong_starts_repaired','wrong_starts'),('Все успешные завершения','passed','total')]:
            values=[]
            for arm in ['lora','full']:
                a=reports['parent_'+arm]['self']['summary'];b=fixed[arm]['self']['summary'];values.append(str(a[field])+' → '+str(b[field])+' / '+str(a[den]))
            lead.append('| '+label+' | '+' | '.join(values)+' |')
        lead += ['', 'Совместного улучшения не получено: порчи кода меньше, но успешных исправлений тоже меньше. Родительские профили сохранены; кандидаты 6000 остаются исследовательскими артефактами.', '']
        lines[2:2]=lead
    from bh_eval import key as development_key
    lines += ['## Промежуточные результаты development','',
        '| Ветка / шаг | raw исправлено | raw ложный DONE | raw порча | self исправлено | self ложный DONE | self порча | Допущен |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for arm in ['lora','full']:
        parent_dev=read(root/f'parent-{arm}-development.json')
        for step in [0,1000,3000,6000]:
            d=parent_dev if step==0 else read(root/arm/f'development-{step}.json')
            raw,selfcheck=[d[g]['summary']for g in ['raw','self']]
            lines.append(f'| {arm}/{step} | {raw["wrong_starts_repaired"]}/{raw["wrong_starts"]} | {raw["false_DONE"]}/{raw["total"]} | {raw["correct_starts_corrupted"]}/{raw["correct_starts"]} | {selfcheck["wrong_starts_repaired"]}/{selfcheck["wrong_starts"]} | {selfcheck["false_DONE"]}/{selfcheck["total"]} | {selfcheck["correct_starts_corrupted"]}/{selfcheck["correct_starts"]} | {bool(development_key(d,parent_dev)[0])} |')
    lines += ['', 'Допуск требует одновременно всех защищённых показателей и языковых ограничений. Это воспроизведение зафиксированного правила, не новый выбор по закрытым ответам.', '']
    if len(fixed)==2:
        lines += ['## Дополнительная фиксированная оценка шага 6000','',
            'Эта оценка объявлена до открытия closed, после промежуточного development: она показывает эффект фактически обученных финальных весов, даже если защитный отбор оставил родителей. Шаг фиксирован заранее, по closed не выбирался. Отдельный драйвер вызывает тот же замороженный evaluator; обучение не перезапускалось. Основной выбор весов остаётся прежним.', '',
            '| Режим / показатель | Адаптеры BF | Адаптеры 6000 | Полная BF | Полная 6000 |','|---|---:|---:|---:|---:|']
        for gate in ['raw','self']:
            for label,field,den in [('Ложный DONE','false_DONE','total'),('Порча','correct_starts_corrupted','correct_starts'),('Исправление','wrong_starts_repaired','wrong_starts'),('Успех','passed','total')]:
                v=[reports['parent_lora'][gate]['summary'],fixed['lora'][gate]['summary'],reports['parent_full'][gate]['summary'],fixed['full'][gate]['summary']]
                lines.append('| '+gate+' / '+label+' | '+' | '.join(str(x[field])+'/'+str(x[den])for x in v)+' |')
        if(ROOT/'fixed-audit-native.json').exists():
            checks=read(ROOT/'fixed-audit-native.json')
            lines += ['', 'Отдельная проверка дополнительных Q4-экспортов: '+json.dumps({a:{k:v[k]for k in ['probes','all_equal','mka_bytes']}for a,v in checks['models'].items()},ensure_ascii=False), '']
        lines += ['', 'Q4-экспорты дополнительных моделей: export/fixed6000_lora и export/fixed6000_full. Они не использовались для переназначения основного выбора.', '', '| Фиксированная ветка | Показатель | Разность, п.п. | 95% bootstrap |', '|---|---|---:|---:|']
        for arm,values in stats['fixed6000_paired'].items():
            for label,v in values.items():
                lo,hi=v['bootstrap_95'];lines.append(f'| {arm} | {label} | {100*v["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} |')
        lines.append('')
    elif(ROOT/'fixed-audit-plan.json').exists():
        lines += ['', 'Дополнительная фиксированная оценка 6000 объявлена до closed и ещё выполняется; этот отчёт пока описывает только основной выбор.', '']
    report=HERE/'PAIRED_SPEC_LORA_FULL_RESULTS.md';report.write_text('\n'.join(lines))
    write(root/'report-receipt.json',{'report_sha256':sha(report),'optimizer_updates':12000,'closed_used_for_selection':False})
    print(json.dumps({'report':str(report),'selection':selection},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args();main(a.root)
