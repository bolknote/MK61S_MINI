"""Report the preselected prompt A/B, including real-translation safety costs."""
import json
import time
import collections
from bz_common import ROOT,HERE,read,write,rows,sha,check_frozen
from bz_runtime import shorten
from by_finish import analyze,transitions
from bl_spec import install
from bl_vm import CachedVM


def first_choices(baseline,compact):
    left={r['id']:r for r in baseline['own']['records']};right={r['id']:r for r in compact['own']['records']}
    assert left.keys()==right.keys();counts={};transitions=collections.Counter()
    def label(h):
        g=h['generation']
        if g.get('codec_error'):return 'ERROR:'+g['codec_error']
        if g['action']=='diag':return 'diag:'+f"{g['body'][0]:02X}"
        return g['action']
    for key,a in left.items():
        b=right[key]
        x=next(h for h in a['history']if h.get('generation',{}).get('profile')=='actor')
        y=next(h for h in b['history']if h.get('generation',{}).get('profile')=='actor')
        assert shorten(x['prompt'])==y['prompt'],'Initial state changed beyond compacting static prose'
        cohort='correct_start'if a['initially_correct']else'wrong_start'
        for name,h in [('original',x),('compact',y)]:
            counts.setdefault(cohort,{}).setdefault(name,collections.Counter())[label(h)]+=1
        transitions[cohort+'|'+label(x)+'→'+label(y)]+=1
    return {'all_initial_states_identical_except_static_prose':True,'episodes':len(left),
        'counts':{c:{f:dict(v)for f,v in modes.items()}for c,modes in counts.items()},'transitions':dict(transitions)}


def main():
    check_frozen();install();vm=CachedVM();remote=ROOT/'server-results'
    assert read(remote/'controller-complete.json')['all_own_workers_joined']
    assert read(remote/'postflight.json')['Qwen_health']=='200'
    native=read(remote/'native-verification.json');assert native['complete']
    selection=read(remote/'preselected.json');assert not selection['closed_seen']
    output={'complete':True,'optimizer_updates':0,'candidate_formats':1,'selection':selection,
        'panels_are_retired_diagnostics':True,'gold_is_external_answer':True,'panels':{},
        'native_streams':native['streams_verified'],'token_proof':read(ROOT/'CPU-preflight.json')}
    for split in ['development','closed']:
        output['panels'][split]={};goals=rows(ROOT/(split+'.jsonl'))
        for mode in ['gold','own']:
            baseline=read(ROOT/f'baseline-{split}-{mode}.json');compact=read(remote/f'{split}-{mode}.json')
            assert compact['initial_interpretations_equal_frozen_baseline']
            output['panels'][split][mode]={'original':analyze(baseline,goals,vm),'compact':analyze(compact,goals,vm),
                'transition':transitions(baseline,compact,goals),'first_choices':first_choices(baseline,compact)}
            print({'analysis_complete':split+'_'+mode},flush=True)
    write(ROOT/'comparison.json',output)
    report=HERE/'SPEC_COMPACT_PROMPT_RESULTS.md'
    closed=output['panels']['closed'];g0=closed['gold']['original']['summary'];g1=closed['gold']['compact']['summary']
    o0=closed['own']['original']['summary'];o1=closed['own']['compact']['summary']
    lines=['# Сокращение запроса к исполнителю без дообучения','',
        f"На прежней панели 256 задач сокращение на 126 токенов меняет завершения с эталонной SPEC {g0['passed']}→{g1['passed']} из 512, с обычным переводчиком BU1500 — {o0['passed']}→{o1['passed']}. Исправления ошибочного кода: gold {g0['wrong_starts_repaired']}→{g1['wrong_starts_repaired']}, own {o0['wrong_starts_repaired']}→{o1['wrong_starts_repaired']}. Формат, выбранный заранее на development: **{selection['chosen_format']}**.",'',
        'Один кандидат, ноль обновлений весов. Менялась только служебная часть обычного запроса исполнителя. Переводчик BU1500, первоначальный разбор и повторный разбор условия, старты, константы, RUN, проверка DONE, откат, 12 действий, контекст 1024 и FP32 KV сохранены. Эталонная SPEC — отдельный диагностический режим с подсказкой извне; режим own использует обычный переводчик без доступа к эталону.','',
        'На 5823 сохранённых запросах (3240 уникальных) проверено дословное сохранение условия, таблицы констант, гипотезы SPEC, кода, публичных входов, фактов RUN, наблюдений и диагноза. Каждый запрос стал на 126 токенов короче. Это измерение одинаковых состояний; в новых траекториях набор состояний различается. Подсказки с ожидаемыми значениями по скрытому условию не добавлялись.','',
        'Использованы прежние development128 и closed256. Это уже использованные диагностические панели, а не новый закрытый экзамен. Правило выбора и единственный кандидат заморожены до генераций: в обоих режимах development минимум +2 верных завершения, не меньше исправлений и доведённых правильных стартов, не больше принятых ложных DONE и итоговой порчи. Число переполнений само по себе не определяет выбор.','',
        f"По development выбран формат **{selection['chosen_format']}**. Все условия выбора: **{selection['all_checks_passed']}**. Выбор сохранён до генераций closed; closed его не меняет. Рабочий профиль приложения и физического устройства не заменён.",'',
        '| Панель | SPEC | Формат | Завершено | Верный старт доведён | Ошибочный старт исправлен | Принятые ложные DONE | Итоговая порча | Переполнение | До первого действия |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for split,modes in output['panels'].items():
        for mode,values in modes.items():
            for name in ['original','compact']:
                a=values[name];s=a['summary'];c=a['counts']
                lines.append(f"| {split} | {mode} | {name} | {s['passed']}/{s['total']} | {s['correct_starts_completed']}/{s['correct_starts']} | {s['wrong_starts_repaired']}/{s['wrong_starts']} | {s['false_DONE']} | {s['correct_starts_corrupted']} | {s['context_overflows']} | {c.get('first_actor_call_overflow',0)} |")
    lines+=['','Gold не измеряет самостоятельный перевод условия. При неверной собственной SPEC проверка программы относительно этой SPEC может принять неверное решение; поэтому режим own обязателен для оценки безопасности формата. Ноль итоговой порчи после отката не означает отсутствие неверных предложенных правок.','',
        '| Панель | SPEC | Формат | Неверный WRITE при верном старте | Неверный кандидат перед откатом | Эпизоды с ложными заявлениями DONE | Все ложные заявления / все DONE |',
        '|---|---|---|---:|---:|---:|---:|']
    for split,modes in output['panels'].items():
        for mode,values in modes.items():
            for name in ['original','compact']:
                a=values[name];s=a['summary'];c=a['counts']
                lines.append(f"| {split} | {mode} | {name} | {c.get('correct_start:with_wrong_WRITE',0)} | {c.get('correct_start:wrong_candidate_at_exit',0)} | {s['episodes_with_false_DONE_claims']} | {s['false_DONE_claims']}/{s['all_DONE_claims']} |")
    lines+=['','| Панель | SPEC | Формат | Повторные разборы SPEC | Правильная начальная SPEC испорчена пересмотром |',
        '|---|---|---|---:|---:|']
    for split,modes in output['panels'].items():
        for mode in modes:
            for name in ['original','compact']:
                path=ROOT/f'baseline-{split}-{mode}.json'if name=='original'else remote/f'{split}-{mode}.json'
                value=read(path);r=value['own'];replan=r.get('replan',{})
                lines.append(f"| {split} | {mode} | {name} | {r['summary']['replans']} | {replan.get('correct_to_wrong',0)} |")
    lines+=['','## Причины незавершения','',
        'Категории ниже взаимоисключающие. Меньше переполнений может означать больше отказов или исчерпаний действий; само по себе это не успех.','',
        '| Панель | SPEC | Формат | Успех | Принятый ложный DONE | Отказ | Переполнение | Другая ошибка генерации | Бюджет действий | Верный код без завершения |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for split,modes in output['panels'].items():
        for mode,values in modes.items():
            for name in ['original','compact']:
                a=values[name];o=a['outcomes_exclusive']
                fields=[str(o.get(k,0))for k in ['passed','accepted_false_DONE','abstained','context_overflow','other_generation_error','action_budget']]
                lines.append('| '+split+' | '+mode+' | '+name+' | '+' | '.join(fields)+f" | {a['counts'].get('correct_code_not_finished',0)} |")
    lines+=['','## Первый выбор на одинаковом состоянии','',
        'Для каждого эпизода проверено: первый короткий запрос точно равен сокращённому первому прежнему запросу. Поэтому здесь ещё нет влияния разошедшихся действий, новых RUN или повторного разбора. DIAG 04 означает запрос пересмотра SPEC; при gold эта гипотеза заведомо правильная.','',
        '| Панель | SPEC | Старт | Формат | Первые действия |',
        '|---|---|---|---|---|']
    for split,modes in output['panels'].items():
        for mode,values in modes.items():
            for cohort,formats in values['first_choices']['counts'].items():
                for name,counts in formats.items():
                    text=', '.join(k+'='+str(v)for k,v in sorted(counts.items()))
                    lines.append(f"| {split} | {mode} | {cohort} | {name} | {text} |")
    lines+=['','## Парные изменения','',
        'Короткий минус прежний формат. Интервалы 95% получены по 10 000 парных bootstrap-выборок задач; оба старта задачи остаются вместе. Они не учитывают выбор формата на development и не превращают прежний closed в новый экзамен.','',
        '| Панель | SPEC | Выиграно эпизодов | Потеряно | Завершения, п.п. [95%] | Исправления, п.п. [95%] |',
        '|---|---|---:|---:|---:|---:|']
    for split,modes in output['panels'].items():
        for mode,values in modes.items():
            t=values['transition'];c=t['counts'];cells=[]
            for key in ['completion','repairs']:
                q=t['paired_uncertainty'][key];lo,hi=q['CI95_task_bootstrap'];cells.append(f"{q['delta_percentage_points']:+.2f} [{lo:+.2f}; {hi:+.2f}]")
            lines.append(f"| {split} | {mode} | {c.get('gained',0)} | {c.get('lost',0)} | "+' | '.join(cells)+' |')
    lines+=['','## Условия выбора','']
    for name,passed in selection['checks'].items():lines.append(f"- {name}: {passed}")
    lines+=['','Короткий формат меняет распределение входов старой сети; одинаковые публичные факты не гарантируют одинаковое решение. Этот опыт не меняет и не оценивает ёмкость модели. Результат относится к проверенным числовым AST и данным траекториям, не ко всем программам МК-61.','',
        '## Практический вывод и следующий опыт','',
        'Проверен один способ сокращения, а не все короткие форматы. Убраны дублирующиеся указания и сокращены описания вызовов/DIAG; опыт не отделяет вклад каждой из этих правок. Рост повторных разборов и изменение числа ложных заявлений DONE — наблюдаемые изменения поведения, но не доказательство того, какая конкретная строка их вызвала.','',
        'Следующий небольшой диагностический опыт — раздельно сокращать справку вызовов, DIAG и повторяемые общие правила, сохраняя два других раздела. Выбор делать по development с обеими SPEC, с обязательной проверкой исправлений; экономию токенов учитывать отдельно от качества. Это позволит выбрать данные и формат для адаптации исполнителя без одновременной смены всего протокола.','',
        'Для последующего обучения исполнителя нужны парные состояния в прежнем и выбранном коротком формате с одинаковыми проверенными целями, повтор прежних успешных исправлений и полные циклы. Включать как правильную SPEC, так и неверную гипотезу при правильном/неправильном коде; иначе обучение доверию к SPEC может перенести ошибки переводчика в принятый DONE. Проверять исправления, сохранение кода до отката, повторный разбор и принятые/отклонённые ложные DONE отдельно. Это рекомендации для нового опыта; здесь весов не обучали.','',
        '## Проверка исполнения','',
        f"Первые SPEC в обеих ветках точно совпали с прежними потоками по всем 384 задачам, поэтому менялся именно обычный запрос исполнителя. Проверены {native['streams_verified']} реальных потоков B200/CPU/C++ для исполнителя и BU1500, включая компактные запросы и пересмотр условия. Счётчик обучения не увеличивался.",'',
        f"Один буфер весов: {native['one_weight_buffer_bytes']} байт; KV на host: {native['KV_bytes']} байт; workspace: {native['workspace_bytes']} байт. Скорость и RAM физического PicoCalc не измерены. Все собственные GPU-задачи завершены, Qwen отвечает 200.",'',
        'Артефакты: `.build/mk61-agent-20261106/spec-compact-prompt-v1`; `comparison.json`, `server-results/preselected.json`, `server-results/native-verification.json`.','']
    report.write_text('\n'.join(lines))
    path=HERE/'work-state.json';state=read(path);ledger={k:state.get(k)for k in ['completed_training_runs','total_accounted_optimizer_updates_lower_bound']}
    state.update(active_experiment=None,all_own_jobs_complete=True,phase='compact_prompt_comparison_complete',
        latest_compact_prompt_diagnostic={'phase':'complete','complete':True,'optimizer_updates':0,'directory':str(ROOT),'report':str(report),
            'selection':selection,'native_streams':native['streams_verified'],
            'closed':{m:{f:values[f]['summary']for f in ['original','compact']}for m,values in output['panels']['closed'].items()}},
        next_action='Keep the development-selected format; isolate calls/DIAG/duplicate-guidance prompt changes on development before paired actor-format adaptation and full-cycle training.')
    assert all(state[k]==v for k,v in ledger.items());write(path,state)
    write(ROOT/'finish.json',{'complete':True,'optimizer_updates':0,'training_ledger_unchanged':ledger,'report_sha256':sha(report),'source_sha256':sha(__file__),'unix':time.time()})
    print(json.dumps({'selection':selection,'report':str(report),'closed':state['latest_compact_prompt_diagnostic']['closed'],'native_streams':native['streams_verified'],'ledger':ledger},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
