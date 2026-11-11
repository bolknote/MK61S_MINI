"""Attribute the remaining finite gold-SPEC failures and preserve the training ledger."""
import collections
import copy
import json
import time
from by_common import ROOT,HERE,read,write,rows,sha,check_frozen
from ar_spec import verify,equivalent,spec_text
from bl_spec import install
from bl_vm import CachedVM
from br_finish import paired


def outcome(r):
    if r['pass']:return 'passed'
    if r['finished']:return 'accepted_false_DONE'
    if r['abstained']:return 'abstained'
    errors=[h.get('generation',{}).get('codec_error')for h in r['history']]
    if 'context_overflow' in errors:return 'context_overflow'
    if any(errors):return 'other_generation_error'
    return 'action_budget'


def analyze(report,goals,vm):
    records=report['own']['records'];byid={g['id']:g for g in goals};counts=collections.Counter();examples=[];rows_out=[]
    for r in records:
        goal=byid[r['task_id']];writes=[]
        for h in r['history']:
            if h['kind']=='write':
                good=verify(vm,h['body'],goal['pool'],goal['spec'],goal['audit_inputs'])['status']=='TESTED'
                writes.append({'correct':good,'revision':h['revision']})
        first_wrong=not writes[0]['correct'] if writes else False
        bad_write=any(not h['correct']for h in writes);good_write=any(h['correct']for h in writes)
        key='correct_start' if r['initially_correct']else 'wrong_start';status=outcome(r)
        actor_calls=[h for h in r['history']if h.get('generation',{}).get('profile')=='actor']
        first_overflow=bool(actor_calls and actor_calls[0]['generation'].get('codec_error')=='context_overflow')
        counts['first_actor_call_overflow']+=first_overflow
        counts[key+':first_actor_call_overflow']+=first_overflow
        if status=='context_overflow':
            counts['overflow_after_false_DONE_claim']+=r['false_DONE_claims']>0
            counts['overflow_after_correct_WRITE']+=good_write
        counts[key+':'+status]+=1;counts['outcome:'+status]+=1
        counts['episodes_with_WRITE']+=bool(writes);counts['episodes_with_wrong_WRITE']+=bad_write
        counts[key+':with_wrong_WRITE']+=bad_write;counts[key+':first_WRITE_wrong']+=first_wrong
        counts[key+':with_correct_WRITE']+=good_write
        counts[key+':wrong_candidate_at_exit']+=not r['candidate_correct_at_exit']
        counts[key+':wrong_candidate_rolled_back']+=not r['candidate_correct_at_exit'] and r['rollback']
        counts['correct_code_not_finished']+=r['program_correct']and not r['finished']
        counts['correct_code_context_overflow']+=r['program_correct']and status=='context_overflow'
        counts['all_WRITE_actions']+=len(writes);counts['wrong_WRITE_actions']+=sum(not h['correct']for h in writes)
        row={'id':r['id'],'task_id':r['task_id'],'initially_correct':r['initially_correct'],'family':r['family'],
             'outcome':status,'final_correct':r['program_correct'],'candidate_correct':r['candidate_correct_at_exit'],
             'rollback':r['rollback'],'writes':writes,'replans':r['replans'],
             'first_actor_call_overflow':first_overflow,
             'false_DONE_claims':r['false_DONE_claims'],'history_kinds':[h['kind']for h in r['history']]}
        rows_out.append(row)
        if not r['pass']:
            examples.append({**row,'task':goal['task'],'gold_SPEC':goal['spec'],'gold_formula':spec_text(goal['spec']),
                'initial_body':goal['reference_body']if r['initially_correct']else goal['bad_body'],
                'final_body':r['body'],'candidate_body':r['candidate_at_exit'],
                'last_observation':next((h.get('observation')for h in reversed(r['history'])if h.get('observation')),None),
                'last_codec_error':next((h['generation']['codec_error']for h in reversed(r['history'])if h.get('generation',{}).get('codec_error')),None)})
    return {'summary':report['own']['summary'],'counts':dict(counts),'outcomes_exclusive':{k[8:]:v for k,v in counts.items()if k.startswith('outcome:')},
            'records':rows_out,'failures':examples}


def transitions(baseline,gold,goals):
    left={r['id']:r for r in baseline['own']['records']};right={r['id']:r for r in gold['own']['records']};assert left.keys()==right.keys()
    byid={g['id']:g for g in goals};counts=collections.Counter();records=[]
    for key,a in left.items():
        b=right[key];g=byid[a['task_id']]
        initial=equivalent(a['initial_spec'],g['spec'],g['audit_inputs'])['tested_equal']
        final=a['final_spec_intent']['tested_equal'];change='both_pass'if a['pass']and b['pass']else 'both_fail'if not a['pass']and not b['pass']else 'gained'if b['pass']else 'lost'
        counts[change]+=1;counts[('correct_initial_SPEC:'if initial else'wrong_initial_SPEC:')+change]+=1
        counts[('correct_final_SPEC:'if final else'wrong_final_SPEC:')+change]+=1
        records.append({'id':key,'baseline_initial_SPEC_correct':initial,'baseline_final_SPEC_correct':final,
            'baseline_outcome':outcome(a),'gold_outcome':outcome(b),'transition':change})
    return {'counts':dict(counts),'paired_uncertainty':paired(baseline['own']['records'],gold['own']['records']),'records':records}


def main():
    check_frozen();install();vm=CachedVM();remote=ROOT/'server-results'
    assert read(remote/'controller-complete.json')['all_own_workers_joined']
    assert read(remote/'postflight.json')['Qwen_health']=='200'
    native=read(remote/'native-verification.json');assert native['complete']
    result={'complete':True,'optimizer_updates':0,'oracle_diagnostic':True,'independent_solution_score':False,'panels':{},
            'native_streams':native['streams_verified'],'physical_PicoCalc_measured':False}
    for split in ['development','closed']:
        goals=rows(ROOT/(split+'.jsonl'));gold=read(remote/(split+'-gold.json'));summary={}
        assert all(r['final_spec_intent']['tested_equal']for r in gold['own']['records'])
        for role in ['parent','final']:
            baseline=read(ROOT/f'baseline-{split}-{role}.json')
            summary[role]=analyze(baseline,goals,vm);summary[role]['gold_transition']=transitions(baseline,gold,goals)
        summary['gold']=analyze(gold,goals,vm);result['panels'][split]=summary
        write(ROOT/(split+'-failure-analysis.json'),summary)
    write(ROOT/'comparison.json',result)
    report=HERE/'SPEC_GOLD_CYCLE_DIAGNOSTIC_RESULTS.md'
    last=result['panels']['closed'];a=last['final']['summary'];g=last['gold']['summary'];c=last['gold']['counts']
    lines=['# Диагностика полного цикла при правильной SPEC','',
        f"На прежней панели 256 задач эталонная SPEC меняет завершения с {a['passed']} на {g['passed']} из {g['total']}; успешные исправления — с {a['wrong_starts_repaired']} на {g['wrong_starts_repaired']}. Принятые ложные DONE: {a['false_DONE']}→{g['false_DONE']}; итоговая порча: {a['correct_starts_corrupted']}→{g['correct_starts_corrupted']}. Даже с подсказкой остаются {g['total']-g['passed']} незавершённых эпизодов, из них {g['context_overflows']} с переполнением окна, включая {c.get('first_actor_call_overflow',0)} до первого действия сети.",'',
        'Нулевое дообучение. Эталонная SPEC подставлена при первом разборе условия и каждом штатном повторном разборе. Это диагностическая подсказка извне, а не самостоятельный результат модели и не новый рабочий профиль. Все обычные действия и тела WRITE выдавал прежний Q4-исполнитель.','',
        'Задачи, идентификаторы, формулировки, порядок констант, стартовый код, публичные RUN, проверка DONE, откат, 12 действий и контекст 1024 сохранены. Взяты уже использованные BX-панели: development128 и прежний closed256; новый закрытый тест здесь не создавался. Контрольные результаты взяты из завершённого BX с проверкой файлов и задач. До обучения и проверки вариантов этот опыт не относится.','',
        '| Панель | Переводчик / режим | Завершено | Верный старт доведён | Ошибочный старт исправлен | Принятые ложные DONE | Итоговая порча | Переполнение контекста | Верный итоговый код |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    labels={'parent':'BU1500','final':'BX +1200','gold':'Эталон при каждом разборе'}
    for split,values in result['panels'].items():
        for role in ['parent','final','gold']:
            s=values[role]['summary']
            lines.append(f"| {split} | {labels[role]} | {s['passed']}/{s['total']} | {s['correct_starts_completed']}/{s['correct_starts']} | {s['wrong_starts_repaired']}/{s['wrong_starts']} | {s['false_DONE']} | {s['correct_starts_corrupted']} | {s['context_overflows']} | {s['final_correct_code']} |")
    lines+=['','Ноль итоговой порчи может обеспечиваться откатом и сам по себе не означает сохранение правильного кода при генерации. Предложенные неверные WRITE учитываются отдельно. Отказ, исчерпание бюджета и ошибка генерации считаются незавершением.','',
        '| Панель | Режим | Эпизоды с ложными заявлениями DONE | Всего ложных заявлений DONE | Все заявления DONE |',
        '|---|---|---:|---:|---:|']
    for split,values in result['panels'].items():
        for role in ['parent','final','gold']:
            s=values[role]['summary']
            lines.append(f"| {split} | {labels[role]} | {s['episodes_with_false_DONE_claims']} | {s['false_DONE_claims']} | {s['all_DONE_claims']} |")
    lines+=['','Ложное заявление может быть отклонено упряжью. Поэтому ноль принятых ложных DONE не означает, что исполнитель научился оценивать корректность.','',
        '## Что осталось при эталонной SPEC','',
        '| Панель | Успех | Отказ | Переполнение | Другая ошибка генерации | Бюджет действий | Ложный принятый DONE | Верный код без завершения |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for split,values in result['panels'].items():
        a=values['gold'];o=a['outcomes_exclusive'];c=a['counts']
        lines.append('| '+split+' | '+' | '.join(str(o.get(k,0))for k in ['passed','abstained','context_overflow','other_generation_error','action_budget','accepted_false_DONE'])+f" | {c.get('correct_code_not_finished',0)} |")
    lines+=['','| Панель | Верный старт: неверный WRITE хотя бы раз | Верный старт: неверный кандидат перед откатом | Ошибочный старт: правильный WRITE хотя бы раз | Все неверные WRITE / все WRITE |',
        '|---|---:|---:|---:|---:|']
    for split,values in result['panels'].items():
        c=values['gold']['counts'];s=values['gold']['summary']
        lines.append(f"| {split} | {c.get('correct_start:with_wrong_WRITE',0)}/{s['correct_starts']} | {c.get('correct_start:wrong_candidate_at_exit',0)} | {c.get('wrong_start:with_correct_WRITE',0)}/{s['wrong_starts']} | {c.get('wrong_WRITE_actions',0)}/{c.get('all_WRITE_actions',0)} |")
    lines+=['','| Панель | Переполнение до первого действия сети | Из них при правильном старте | Переполнение после ложного заявления DONE |',
        '|---|---:|---:|---:|']
    for split,values in result['panels'].items():
        c=values['gold']['counts']
        lines.append(f"| {split} | {c.get('first_actor_call_overflow',0)} | {c.get('correct_start:first_actor_call_overflow',0)} | {c.get('overflow_after_false_DONE_claim',0)} |")
    lines+=['','Переполнение до первого действия возникает при построении запроса и не устраняется выбором другого действия моделью. Для него нужен более компактный формат запроса при прежнем окне. Позднее переполнение может быть следствием неверного WRITE, повторных DONE_REJECTED и разросшейся диагностики; одно сокращение текста не гарантирует исправление программы.','']
    lines+=['','## Парные изменения','',
        'Сравниваются одинаковые задачи и оба старта. 95% интервал — 10 000 парных bootstrap-выборок по задачам; он не включает разброс обучения и не делает прежний closed новым экзаменом.','',
        '| Панель | Контроль | Выиграно эпизодов | Потеряно эпизодов | Изменение завершений, п.п. [95%] |',
        '|---|---|---:|---:|---:|']
    for split,values in result['panels'].items():
        for role in ['parent','final']:
            t=values[role]['gold_transition'];c=t['counts'];q=t['paired_uncertainty']['completion'];lo,hi=q['CI95_task_bootstrap']
            lines.append(f"| {split} | {labels[role]} | {c.get('gained',0)} | {c.get('lost',0)} | {q['delta_percentage_points']:+.2f} [{lo:+.2f}; {hi:+.2f}] |")
    lines+=['','Переходы отдельно по исходно правильному/ошибочному разбору сохранены в `comparison.json`. Оставшиеся ошибки при эталонной SPEC нельзя приписывать переводчику: они возникают в обычных действиях исполнителя, взаимодействии с проверкой, контексте или лимите цикла. Этот опыт не разделяет эти четыре причины и не доказывает предел ёмкости.','',
        '## Следующий контролируемый шаг','',
        'Сначала сравнить прежний и компактный запрос к исполнителю без обучения, с теми же входами, эталонной SPEC, проверкой и бюджетом 12/1024. Сохранить условие, SPEC, код, факты RUN, непроверенные случаи, остаток действий и причину последнего отклонения DONE; сократить повторяемую справку и служебную прозу. Выбор формата сделать на development, а не по прежнему closed. Краткий формат меняет распределение входов, поэтому улучшение нужно измерить, оно не обещано заранее.','',
        'После фиксации формата обучать отдельного исполнителя на полных циклах, отделяя этот курс от адаптера перевода: правильная SPEC + ошибочная программа → правильный WRITE; правильная программа → недостающие RUN 00/01 и DONE; DONE_REJECTED → разбор численного контрпримера и исправление. Смешивать с повтором прежних успешных циклов. Для этих числовых AST цели WRITE и правильные переходы можно строить проверенным компилятором и эмулятором; ответы учителя сами по себе не служат проверкой. Проверять и сохранение правильного кода до отката, и успешные исправления, и ложные заявления/принятые DONE по отдельности. Это план нового опыта, обучения здесь не было.','',
        '## Проверка исполнения','',
        f"384 эталона дают прежний эталонный код; исходные ошибочные программы остаются ошибочными. Проверены 768 кодирований SPEC с соблюдением контекста. {native['streams_verified']} реальных потоков исполнителя совпали на B200, CPU и C++. Подставленные ответы oracle не учитывались как генерации нейросети.",
        f"Исполнитель MKA `{native['actor_mka_sha256']}`; один буфер весов {native['one_weight_buffer_bytes']} байт, фактически выделенный на host KV {native['KV_bytes']} байт, workspace {native['workspace_bytes']} байт. Скорость и память физического PicoCalc не измерены.",'',
        'Все собственные GPU-задачи завершены, Qwen отвечает 200. Веса и рабочий профиль не заменены; обучающих обновлений 0.','',
        'Артефакты: `.build/mk61-agent-20261106/spec-gold-cycle-diagnostic-v1`; `comparison.json`, `development-failure-analysis.json`, `closed-failure-analysis.json`, `server-results/native-verification.json`.','']
    report.write_text('\n'.join(lines))
    path=HERE/'work-state.json';state=read(path);ledger={k:state.get(k)for k in ['completed_training_runs','total_accounted_optimizer_updates_lower_bound']}
    state.update(active_experiment=None,all_own_jobs_complete=True,phase='gold_SPEC_cycle_diagnostic_complete',
        latest_gold_cycle_diagnostic={'phase':'complete','complete':True,'optimizer_updates':0,'directory':str(ROOT),'report':str(report),
            'independent_solution_score':False,'native_streams':native['streams_verified'],
            'closed_completed':{k:v['summary']['passed']for k,v in result['panels']['closed'].items()}},
        next_action='Use gold-SPEC failure attribution to choose one controlled actor/harness experiment; do not promote the oracle as an autonomous model.')
    assert all(state[k]==v for k,v in ledger.items());write(path,state)
    write(ROOT/'finish.json',{'complete':True,'optimizer_updates':0,'training_ledger_unchanged':ledger,'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print(json.dumps({'report':str(report),'closed':{role:data['summary']for role,data in result['panels']['closed'].items()},'native_streams':native['streams_verified'],'ledger':ledger},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
