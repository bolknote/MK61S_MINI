"""Attribute each prompt-section effect without selecting by the retired audit panel."""
import collections
import json
import time
from ca_common import ROOT,HERE,VARIANTS,read,write,rows,sha,check_frozen
from ca_runtime import shorten
from by_finish import analyze,transitions
from bl_spec import install
from bl_vm import CachedVM

LABELS={'original':'Прежний','joint':'Все три вместе','calls':'Справка вызовов','diag':'Справка DIAG','notes':'Общие правила'}


def first_choices(baseline,current,variant):
    a={r['id']:r for r in baseline['own']['records']};b={r['id']:r for r in current['own']['records']};assert a.keys()==b.keys()
    counts={};changes=collections.Counter()
    def label(h):
        g=h['generation']
        if g.get('codec_error'):return 'ERROR:'+g['codec_error']
        return 'diag:'+f"{g['body'][0]:02X}"if g['action']=='diag'else g['action']
    for key,left in a.items():
        right=b[key];x=next(h for h in left['history']if h.get('generation',{}).get('profile')=='actor')
        y=next(h for h in right['history']if h.get('generation',{}).get('profile')=='actor')
        assert shorten(x['prompt'],'all'if variant=='joint'else variant)==y['prompt'],(key,variant)
        cohort='correct_start'if left['initially_correct']else'wrong_start'
        for name,h in [('original',x),('changed',y)]:counts.setdefault(cohort,{}).setdefault(name,collections.Counter())[label(h)]+=1
        changes[cohort+'|'+label(x)+'→'+label(y)]+=1
    return {'all_initial_states_identical_except_selected_static_section':True,'episodes':len(a),
        'counts':{c:{f:dict(v)for f,v in modes.items()}for c,modes in counts.items()},'transitions':dict(changes)}


def point(a):
    return {k:a[k]for k in ['passed','total','correct_starts_completed','wrong_starts_repaired','false_DONE','correct_starts_corrupted','context_overflows','replans']}


def main():
    check_frozen();install();vm=CachedVM();root=ROOT/'server-results'
    assert read(root/'controller-complete.json')['all_own_workers_joined']and read(root/'postflight.json')['Qwen_health']=='200'
    native=read(root/'native-verification.json');assert native['complete']and native['all_three_variants_verified']
    selection=read(root/'preselected.json');assert not selection['closed_seen'];audit=selection['audit_variant']
    proof=read(ROOT/'CPU-preflight.json');result={'complete':True,'optimizer_updates':0,'panels_are_retired_diagnostics':True,
        'selection':selection,'tokens_saved':proof['tokens_saved'],'native_streams':native['streams_verified'],'panels':{}}
    for split in ['development','closed']:
        goals=rows(ROOT/(split+'.jsonl'));result['panels'][split]={}
        for mode in ['gold','own']:
            baseline=read(ROOT/f'baseline-{split}-{mode}.json');values={'original':analyze(baseline,goals,vm)}
            for variant in [*VARIANTS,'joint']if split=='development'else[audit]:
                current=read(ROOT/f'joint-development-{mode}.json')if variant=='joint'else read(root/f'{split}-{variant}-{mode}.json')
                entry=analyze(current,goals,vm);entry.update(transition=transitions(baseline,current,goals),
                    first_choices=first_choices(baseline,current,variant),replan=current['own']['replan'])
                values[variant]=entry
            result['panels'][split][mode]=values
            print({'analysis_complete':split+'_'+mode,'variants':list(values)},flush=True)
    write(ROOT/'comparison.json',result)
    report=HERE/'SPEC_PROMPT_PARTS_RESULTS.md'
    closed=result['panels']['closed'];a=closed['own']['original']['summary'];b=closed['own'][audit]['summary']
    lines=['# Отдельные сокращения трёх разделов промпта','',
        f"На development выбран формат **{selection['chosen_format']}**; для второй панели заранее зафиксирован вариант **{audit}**. С BU1500 на прежних 256 задачах завершения {a['passed']}→{b['passed']} из 512, исправления {a['wrong_starts_repaired']}→{b['wrong_starts_repaired']} из 256 (прежний → новый). Рабочий профиль не заменён.",'',
        'Дообучения не было: исполнитель Q4 и переводчик BU1500 неизменны. Три варианта меняют по одному разделу прежнего запроса: список вызовов, объяснение DIAG, повторяемые общие правила. Остальные два раздела сохраняются дословно. Сокращения в точности взяты из предыдущего неудачного совместного варианта; новые формулировки здесь не подбирались.','',
        f"Экономия токенов на одинаковом состоянии: вызовы — {proof['tokens_saved']['calls']}, DIAG — {proof['tokens_saved']['diag']}, общие правила — {proof['tokens_saved']['notes']}. На {proof['real_actor_prompts_checked']} сохранённых запросах ({proof['unique_prompts']} уникальных) подтверждено сохранение всех публичных переменных полей, углового режима и остатка действий. Все три сокращения вместе точно восстанавливают прежний BZ-вариант с экономией 126 токенов.",'',
        'Во всех полных циклах сохранены условие, константы, стартовый код, открытые входы, эмулятор, RUN, проверка DONE, откат, 12 действий и контекст 1024 с FP32 KV. Начальные SPEC и все их токены совпали с прежними ответами. gold подставляет эталон при первом и повторном разборе и не является самостоятельным решением; own использует обычный BU1500 без эталона. Первые запросы каждого эпизода дополнительно проверены: они отличаются от прежних только выбранным сокращением, ещё до расхождения действий.','',
        'Использованы уже изученные development128 и closed256: это диагностические панели, не новый закрытый экзамен. Каждый из трёх вариантов проверен на development в обоих режимах. Выбор заморожен до второй панели: минимум +2 правильных завершения в обоих режимах, не меньше исправлений и доведённых правильных стартов, не больше принятых ложных DONE и итоговой порчи. Из прошедших вариантов предпочтение по own-завершениям, own-исправлениям, gold-завершениям, gold-исправлениям, безопасности, затем экономии токенов. Если никто не прошёл, сохраняется original; лучший новый вариант проверяется только для диагностики.','',
        '## Полные циклы','',
        '| Панель | SPEC | Сокращённый раздел | Завершено | Верный старт доведён | Ошибочный исправлен | Принятые ложные DONE | Итоговая порча | Переполнение | До первого действия |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for split,modes in result['panels'].items():
        for mode,values in modes.items():
            for variant,entry in values.items():
                s=entry['summary'];c=entry['counts']
                lines.append(f"| {split} | {mode} | {LABELS[variant]} | {s['passed']}/{s['total']} | {s['correct_starts_completed']} | {s['wrong_starts_repaired']} | {s['false_DONE']} | {s['correct_starts_corrupted']} | {s['context_overflows']} | {c.get('first_actor_call_overflow',0)} |")
    lines+=['','Итоговая порча измерена после отката неподтверждённого кандидата; неверные предложения WRITE считаются отдельно. Принятый ложный DONE отличается от ложного заявления, которое отклонила проверка.','',
        '| Панель | SPEC | Раздел | Неверный WRITE при верном старте | Ложных заявлений DONE / всех DONE | Повторных разборов |',
        '|---|---|---|---:|---:|---:|']
    for split,modes in result['panels'].items():
        for mode,values in modes.items():
            for variant,entry in values.items():
                s=entry['summary'];c=entry['counts']
                lines.append(f"| {split} | {mode} | {LABELS[variant]} | {c.get('correct_start:with_wrong_WRITE',0)} | {s['false_DONE_claims']}/{s['all_DONE_claims']} | {s['replans']} |")
    lines+=['','## Первый ответ на одинаковом состоянии','',
        'DIAG 04 — запрос пересмотра SPEC. В gold такая гипотеза уже правильна. Ошибки context_overflow/incomplete обозначают ошибку генерации, а не отдельную команду модели.','',
        '| Панель | SPEC | Раздел | Старт | Первый ответ |',
        '|---|---|---|---|---|']
    for split,modes in result['panels'].items():
        for mode,values in modes.items():
            sample=next(entry for variant,entry in values.items()if variant!='original')
            for cohort,formats in sample['first_choices']['counts'].items():
                counts=formats['original'];text=', '.join(k+'='+str(v)for k,v in sorted(counts.items()))
                lines.append(f"| {split} | {mode} | {LABELS['original']} | {cohort} | {text} |")
            for variant,entry in values.items():
                if variant=='original':continue
                for cohort,formats in entry['first_choices']['counts'].items():
                    counts=formats['changed'];text=', '.join(k+'='+str(v)for k,v in sorted(counts.items()))
                    lines.append(f"| {split} | {mode} | {LABELS[variant]} | {cohort} | {text} |")
    lines+=['','## Парная неопределённость','',
        'Изменение относительно original, п.п.; 95% интервалы по 10 000 парных bootstrap-выборок задач, оба старта остаются вместе. Интервалы не учитывают выбор лучшего варианта на development и не превращают повторную панель в новый экзамен.','',
        '| Панель | SPEC | Раздел | Выиграно / потеряно эпизодов | Завершения [95%] | Исправления [95%] |',
        '|---|---|---|---:|---:|---:|']
    for split,modes in result['panels'].items():
        for mode,values in modes.items():
            for variant,entry in values.items():
                if variant=='original':continue
                t=entry['transition'];c=t['counts'];cells=[]
                for key in ['completion','repairs']:
                    q=t['paired_uncertainty'][key];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.2f} [{lo:+.2f}; {hi:+.2f}]")
                lines.append(f"| {split} | {mode} | {LABELS[variant]} | {c.get('gained',0)} / {c.get('lost',0)} | "+' | '.join(cells)+' |')
    lines+=['','## Заранее заданный выбор','']
    for variant,decision in selection['decisions'].items():
        lines+=['',f"{LABELS[variant]}: eligible={decision['eligible']}, key={decision['key']}.",'']
        for key,passed in decision['checks'].items():lines.append(f'- {key}: {passed}')
    lines+=['','Одиночные сокращения показывают эффект конкретного раздела при двух остальных прежних. Все попарные сочетания здесь не измерялись; взаимодействия частей нельзя объявлять установленными только по трём одиночным вариантам и прежнему совместному. Результат относится к этим числовым AST и старым весам, а не ко всем форматам и не к пределу ёмкости 3M.','',
        '## Следующий контролируемый обучающий опыт','',
        f"Кандидат формата для адаптации исполнителя: {audit}, зафиксированный по development. Переводчик BU1500 и проверку оставить замороженными. Исполнителя начинать от прежних весов, обучать парным состояниям original/{audit} с одинаковыми проверенными целями и повтором прежних успешных исправлений. Это план следующего опыта; в текущем весов не обучали.",'',
        'В курс включить: правильная SPEC + неправильный код → правильный WRITE; правильный код → недостающие RUN и DONE; неправильная SPEC при правильном/неправильном коде → DIAG 04 и повторный разбор без изменения программы; после исчерпания пересмотра неверной гипотезы → UNSURE. Исправления после DONE_REJECTED должны опираться на реальное численное контрпримерное состояние. Правильный код и подтверждённые результаты RUN не должны теряться при пересмотре условия. Цели WRITE и исходы циклов проверять компилятором и эмулятором.','',
        'Выбирать чекпойнт по полным циклам, сохранению прежних исправлений, ложным DONE и порче до/после отката, в обоих режимах SPEC. После выбора нужен новый заранее закрытый набор русских задач и Q4-проверка. Эти повторно изученные панели полезны для диагностики и регрессии, но не заменяют новый экзамен.','',
        '## Исполнение и артефакты','',
        f"Все {native['streams_verified']} проверенных реальных потоков исполнителя и переводчика совпали на B200, CPU и C++; представлены все три сокращения. Один буфер весов {native['one_weight_buffer_bytes']} байт, host-KV {native['KV_bytes']} байт, workspace {native['workspace_bytes']} байт. Физический PicoCalc не измерялся.",'',
        'Обучающих обновлений 0. Все собственные GPU-задачи завершены, Qwen отвечает 200. Профиль приложения и устройства не заменён.','',
        'Артефакты: `.build/mk61-agent-20261106/spec-prompt-parts-v1`; `comparison.json`, `server-results/preselected.json`, `server-results/audit-roles.json`, `server-results/native-verification.json`.','']
    report.write_text('\n'.join(lines))
    path=HERE/'work-state.json';state=read(path);ledger={k:state.get(k)for k in ['completed_training_runs','total_accounted_optimizer_updates_lower_bound']}
    brief={split:{mode:{v:point(e['summary'])for v,e in values.items()}for mode,values in modes.items()}for split,modes in result['panels'].items()}
    state.update(active_experiment=None,all_own_jobs_complete=True,phase='prompt_parts_comparison_complete',
        latest_prompt_parts_diagnostic={'phase':'complete','complete':True,'optimizer_updates':0,'directory':str(ROOT),'report':str(report),
            'selection':selection,'native_streams':native['streams_verified'],'summary':brief},
        next_action=f'Prepare a separate actor-only Q4 adaptation on paired original/{audit} states, emulator-verified WRITE/RUN/DONE, wrong-SPEC DIAG04/UNSURE cases and old repair replay; keep BU1500 and the mechanical gate fixed, select before a fresh closed test.')
    assert all(state[k]==v for k,v in ledger.items());write(path,state)
    write(ROOT/'finish.json',{'complete':True,'optimizer_updates':0,'training_ledger_unchanged':ledger,'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print(json.dumps({'report':str(report),'selection':selection,'summary':brief,'native_streams':native['streams_verified'],'ledger':ledger},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
