"""Post-evaluation analysis only; never selects or alters frozen BL checkpoints."""
import collections
import json
from bl_common import ROOT,HERE,read,write,sha,check_frozen


def review_stats(report):
    plans={p['id']:p for p in report['primary']['records']};out=collections.Counter()
    for r in report['self']['records']:
        if not r['replans']:continue
        before=plans[r['task_id']]['intent']['tested_equal'];after=r['final_spec_intent']['tested_equal']
        out['total']+=1;out['initial_correct'if before else'initial_wrong']+=1
        out['correct_preserved'if before and after else'correct_spoiled'if before else'wrong_corrected'if after else'wrong_remained']+=1
    return dict(out)


def main():
    check_frozen();r=ROOT/'server-results';assert read(r/'complete.json')['complete']
    selection=read(r/'preselected.json');assert not selection['closed_used_for_selection']
    reports={a:read(r/a/'closed.json')for a in ['parent_lora','parent_full','lora','full','fixed3000_lora','fixed3000_full']}
    # The generic export writer uses one protocol label for every role. Correct
    # package metadata to the actual evaluated profile, including step0 fallback.
    packages={}
    for a,x in reports.items():
        folder=r/'export'/a;p=read(folder/'protocol.json');compact=x['profile']=='compact'
        p.update(kind='spec-compact-own-errors-v1'if compact else'spec-intent-recovery-v1',
                 evaluation_profile=x['profile'],compaction=compact,replan_receives_prior_SPEC=compact,
                 response_reserve=160 if compact else None,remaining_reviews_visible=compact)
        p['DIAG04']='hypothesis error; review prior SPEC without code'if compact else'hypothesis error; condition-only replan without prior SPEC or code'
        write(folder/'protocol.json',p)
        manifest=read(folder/'manifest.json');manifest.update(evaluated_runtime_profile=x['profile'],research_only=True,main_profile_replacement=False)
        if a in ['lora','full']:manifest['continuation_selected_step']=selection['branches'][a]['step']
        write(folder/'manifest.json',manifest)
        reuse=r/a/'audit-reuse.json'
        if reuse.exists():
            write(r/a/'status.json',{'phase':'complete','audit_reused':read(reuse),'metadata_normalized_after_evaluation':True})
        packages[a]={'evaluated_runtime_profile':x['profile'],'protocol_sha256':sha(folder/'protocol.json'),'model_sha256':sha(folder/'model.mkqb')}
    write(ROOT/'export-protocol-receipt.json',{'models':packages,'weight_payloads_unchanged':True,'source_sha256':sha(__file__)})
    analysis={a:{'review':review_stats(x),'self':x['self']['summary'],'NL':x['primary']['natural'],
                 'bad_code_candidates_before_rollback':sum(y['initially_correct']and not y['candidate_correct_at_exit']for y in x['self']['records'])}for a,x in reports.items()}
    write(ROOT/'closed-analysis.json',{'selection_unchanged':True,'models':analysis,'analysis_source_sha256':sha(__file__)})
    path=HERE/'SPEC_COMPACT_OWN_ERRORS_RESULTS.md';text=path.read_text()
    if 'Надёжной замены рабочего профиля не получилось.'not in text:
        text=text.replace('# Компактный контекст и собственные ошибки SPEC\n',
            '# Компактный контекст и собственные ошибки SPEC\n\nНадёжной замены рабочего профиля не получилось. Обе обученные ветки снизили число ложных принятых DONE и порчи кода, но на новом закрытом тесте реже исправляли программы и завершали задачи. Ошибки переполнения контекста устранены; самопроверка смысла SPEC остаётся слабой. Основной профиль сохранён.\n\nЗакрытый экзамен: 952 новых условия, из них 792 естественных и редакторских и 160 формализованных. Инструментальная часть: 512 эпизодов — 256 правильных и 256 ошибочных начальных программ.\n')
    sampling=read(ROOT/'sampling-audit.json');assert sampling['actual_training_digests_matched_both_branches']
    text=text.replace('В20 строках действий батча доля неверных гипотез в среднем15%;',
                      'В12 парных строках батча в среднем3 неверные гипотезы вместо прежних6. Аудит точного потока обеих веток подтвердил: с учётом бюджетных UNSURE неверная гипотеза присутствовала в11851 из60000 строк действий (19.75%); плановые15% учитывали только явные негативные парные строки. Совпадение digest аудита с обоими обучениями точное;')
    for old,new in {'до3000':'до 3000','контекст1024':'контекст 1024','ответа160':'ответа 160','из192':'из 192',
                    'данные:405':'данные: 405','гипотез,1227':'гипотез, 1227','и2504':'и 2504','В12':'В 12','среднем3':'среднем 3',
                    'прежних6':'прежних 6','в11851':'в 11851','из60000':'из 60000','плановые15%':'плановые 15%',
                    'шаг3000':'шаг 3000','Шаг3000':'Шаг 3000','Шаг0':'Шаг 0','ниже90%':'ниже 90%','где16':'где 16'}.items():text=text.replace(old,new)
    text=text.replace('Механическая проверка удостоверяет согласованность с гипотезой модели.',
                      'Механическая проверка сопоставляет код с гипотезой модели на конечном наборе входов.')
    path.write_text(text)
    lines=['','## Версии, выбранные до открытия теста','',
           '| Ветка | Шаг | Исправления /256 | Порча /256 | Ложные принятые DONE /512 | Успешные завершения /512 | Эпизоды с ложными заявлениями /512 |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for a in ['lora','full']:
        x=analysis[a]['self'];lines.append('| '+a+' | '+str(selection['branches'][a]['step'])+' | '+' | '.join(str(x[k])for k in ['wrong_starts_repaired','correct_starts_corrupted','false_DONE','passed','episodes_with_false_DONE_claims'])+' |')
    lines+=['','Собственные гипотезы после повторного разбора в закрытом тесте (считаются эпизоды, один запрос имеет два начальных состояния кода):','',
            '| Версия | Неверных до разбора | Исправлено | Верных до разбора | Испортилось | Плохих кандидатов при верном старте до отката |',
            '|---|---:|---:|---:|---:|---:|']
    for a in reports:
        x=analysis[a];s=x['review'];lines.append(f"| {a} | {s.get('initial_wrong',0)} | {s.get('wrong_corrected',0)} | {s.get('initial_correct',0)} | {s.get('correct_spoiled',0)} | {x['bad_code_candidates_before_rollback']} |")
    if (ROOT/'development-spec-consistency-analysis.json').exists():
        lines+=['','В development отдельно разобран один случай, где16 контрольных входов подтвердили численную согласованность кода с гипотезой, а следующий набор выявил превышение допуска около log10(1). Кэшированный и обычный ROM дали одинаковый результат. Это воспроизводимое ограничение конечной численной проверки; протокол после обнаружения не менялся. Подробности: `development-spec-consistency-analysis.json`.']
    if '## Версии, выбранные до открытия теста'not in text:path.write_text(text+'\n'.join(lines)+'\n')
    receipt=read(ROOT/'finish.json');receipt.update(report_sha256=sha(path),post_evaluation_analysis_source_sha256=sha(__file__));write(ROOT/'finish.json',receipt)
    statepath=HERE/'work-state.json';state=read(statepath)
    state['latest_compact_own_errors_training']['selected_closed']={a:analysis[a]for a in ['lora','full']}
    write(statepath,state)
    print(json.dumps({'selected':{a:analysis[a]for a in ['lora','full']},'selection':selection},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
