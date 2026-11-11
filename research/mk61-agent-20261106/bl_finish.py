"""Record completed training, paired closed-test outcomes and exact Q4 inference."""
import json
import time
from bl_common import ROOT,HERE,read,write,sha,check_frozen


def main():
    check_frozen();r=ROOT/'server-results'
    for n in ['complete.json','native-verification.json','postflight.json']:assert read(r/n)['complete']
    updates={a:read(r/a/'training.json')['optimizer_updates']for a in ['lora','full']}
    assert updates=={'lora':3000,'full':3000}
    assert read(r/'lora/training.json')['draw_digest']==read(r/'full/training.json')['draw_digest']
    selection=read(r/'preselected.json');scores={};changes={}
    lines=['# Компактный контекст и собственные ошибки SPEC', '',
        'Обе ветки дообучены до3000 шагов от последних BJ fixed6000 весов. Q4 на каждом проходе; контекст1024, резерв ответа160, вычисления и KV FP32. Основной профиль и прошивка не заменялись.','',
        'Без обучения короткий промпт убрал переполнения, но ухудшил действия. На прежнем development: LoRA150→147 успешных завершений из192; full161→140. После этого обе ветки обучались именно используемому короткому формату.','',
        'Учебные данные:405 собственных ошибочных гипотез,1227 правильных контрольных гипотез и2504 реальных состояний из уже открытого прежнего экзамена. Корректность повторно проверена на полном старом наборе входов. При повторном разборе доступны условие и прежняя SPEC, текущий код скрыт. Правильная гипотеза сохраняется дословно. В20 строках действий батча доля неверных гипотез в среднем15%; старые успешные исправления и оба RUN сохранены.','',
        'DeepSeek-V4.1-Flash подготовил новые формулировки и дважды проверил новые естественные тестовые условия вслепую, без исходного AST. Это один учитель, а не независимая человеческая проверка. Числа, целевые выражения и отложенные сочетания операций отделены до обучения. Видимые в обучении гипотезы и распознаваемый код тоже проверены на отсутствие отложенных сочетаний.','',
        '## Новый закрытый тест: родитель → фактически обученный шаг3000','',
        'Родитель использует прежний рабочий длинный протокол, обученная версия — компактный протокол с просмотром прежней SPEC. Это сравнение полного предложенного изменения. Успешное исправление требует правильного кода, необходимых RUN и принятого DONE.','',
        '| Ветка | Исправления /256 | Порча правильного /256 | Ложные принятые DONE /512 | Успешные завершения /512 | Эпизоды с ложными заявлениями DONE /512 |',
        '|---|---:|---:|---:|---:|---:|']
    keys=['wrong_starts_repaired','correct_starts_corrupted','false_DONE','passed','episodes_with_false_DONE_claims']
    for arm in ['lora','full']:
        old=read(r/('parent_'+arm)/'closed.json');new=read(r/('fixed3000_'+arm)/'closed.json')
        a=old['self']['summary'];b=new['self']['summary'];scores[arm]={'parent':a,'trained':b,'parent_NLU':old['primary']['natural'],'trained_NLU':new['primary']['natural']}
        lines.append('| '+arm+' | '+' | '.join(f'{a[k]} → {b[k]}'for k in keys)+' |')
        before={x['id']:x for x in old['self']['records']};after={x['id']:x for x in new['self']['records']}
        assert before.keys()==after.keys()
        changes[arm]={'completion_gained':sum(not before[k]['pass']and after[k]['pass']for k in before),
                      'completion_lost':sum(before[k]['pass']and not after[k]['pass']for k in before),
                      'false_DONE_removed':sum(before[k]['finished']and not before[k]['program_correct']and not(after[k]['finished']and not after[k]['program_correct'])for k in before),
                      'false_DONE_added':sum(after[k]['finished']and not after[k]['program_correct']and not(before[k]['finished']and not before[k]['program_correct'])for k in before)}
    lines+=['','Перевод русских условий без цикла инструментов:','','| Ветка | Родитель | Шаг3000 |','|---|---:|---:|']
    for arm in ['lora','full']:
        a=scores[arm]['parent_NLU'];b=scores[arm]['trained_NLU'];lines.append(f"| {arm} | {a['passed']}/{a['total']} | {b['passed']}/{b['total']} |")
    lines+=['','Выбор checkpoint выполнен только на новом development до открытия закрытых ответов. Защищаются ложные принятые DONE, порча, исправления, завершения и эпизоды с ложными заявлениями; также сохраняются язык и структурированные задачи. Низкое число ошибок за счёт потери завершений не проходит. Компактный необученный родитель дополнительно защищается только при покрытии не ниже90% рабочего родителя.','',
            '| Ветка | Выбранный шаг |','|---|---:|',*[f"| {a} | {selection['branches'][a]['step']} |"for a in ['lora','full']], '',
            'Шаг0 означает сохранение прежних весов и прежнего протокола. Независимо от выбора выше приведены результаты реально обученных3000 шагов. Разница между development и новым тестом также считается результатом, а не основанием подбирать другой checkpoint.','',
            '## Проверка и ограничения','',
            '- Результаты и все траектории: `.build/mk61-agent-20261106/spec-compact-own-errors-v1/server-results/`. Заморозка данных и программы: `frozen.json`. Артефакты Q4/HF/MKA находятся в `server-results/export/`.',
            '- Native-проверка сравнивает потоки токенов B200, CPU и C++ на реальных запросах этого теста. На физическом PicoCalc скорость и память не измерялись; новая упряжь пока исполняется на компьютере.',
            '- Механическая проверка удостоверяет согласованность с гипотезой модели. Она не доказывает правильность понимания русского условия. Семантическая правильность здесь оценивается отдельно по закрытому эталону.',
            '- Откат незавершённого WRITE сохраняется. Порча до отката и ложные заявления DONE остаются в полных траекториях; принятые ложные DONE считаются отдельно.',
            '- Проверки конечным числом входов не доказывают корректность произвольной программы. Проверены прямолинейные выражения и запись результата; циклы и ветвления не охвачены.','']
    report=HERE/'SPEC_COMPACT_OWN_ERRORS_RESULTS.md';report.write_text('\n'.join(lines))
    summary={'complete':True,'optimizer_updates':sum(updates.values()),'selection':selection,'scores':scores,'paired_changes':changes,'main_profile_changed':False,'report':str(report)}
    write(ROOT/'summary.json',summary)
    path=HERE/'work-state.json';state=read(path);entry=state['latest_compact_own_errors_training']
    if not entry.get('ledger_accounted'):
        state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=sum(updates.values())
    entry.update(phase='complete',complete=True,ledger_accounted=True,optimizer_updates=sum(updates.values()),report=str(report),scores=scores,selection=selection)
    state['active_experiment']=None;state['all_own_jobs_complete']=True;write(path,state)
    write(ROOT/'finish.json',{'complete':True,'optimizer_updates':sum(updates.values()),'ledger_accounted':True,'report_sha256':sha(report),'unix':time.time()})
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
