"""Paired report; the primary candidate is selected before the new audit."""
import argparse
import collections
import json
from pathlib import Path
import random
import re

from semantic_common import read,write_json,sha


def semantic_diagnostics(report,tasks):
    from course_common import parse_prefix
    from course_eval import grading_tasks
    from compose_common import opcount
    from tasks import compile_expr,registers_used,value_of
    from harness import close_number
    graded={t['id']:t for t in grading_tasks(tasks.values())};counts=collections.Counter()
    for level in [1,2,3]:
        for row in report['metrics'][f'level{level}']['program']['details']:
            counts['total']+=1;task=graded[row['id']]
            match=re.search(r'<calc>(.*?)</calc>',row['reply'],re.S)
            try:expr=parse_prefix(match.group(1))if match else None
            except (ValueError,TypeError,AttributeError):expr=None
            if expr is None:counts['invalid_or_missing_self_calc']+=1;continue
            counts['valid_self_calc']+=1
            counts['self_calc_to_hex_exact']+=compile_expr(expr)+[0x50]==row['code']
            try:correct=all(close_number(str(value_of(expr,c['registers'])),c['expected_X'])for c in task['public_tests']+task['hidden_tests'])
            except (ValueError,ArithmeticError,KeyError):correct=False
            counts['self_calc_correct_numeric']+=correct
            if row['pass']:continue
            needed=registers_used(task['expression']);used=registers_used(expr)
            counts['failed_programs_with_calc']+=1
            counts['failure_missing_needed_input']+=bool(needed-used)
            counts['failure_extra_unused_input']+=bool(used-needed)
            counts['failure_wrong_operation_count']+=opcount(expr)!=task['level']
    return {'counts':dict(counts),'failure_categories_overlap':True,'compiler_used_only_for_posthoc_diagnosis':True,'not_used_for_generation_or_grading':True}


def compact(row):
    return {'levels':{str(k):{kind:{x:row['metrics'][f'level{k}'][kind][x]for x in ['passed','total','rate']}for kind in ['parse','program']}for k in [1,2,3]},
      'program_total':sum(row['metrics'][f'level{k}']['program']['passed']for k in [1,2,3]),
      'formal':[row['formal']['passed'],row['formal']['total']],
      'tools':[row['tool_rollouts']['passed'],row['tool_rollouts']['total']],
      'language_nll':row['public_language']['nll'],
      'long_context':{k:{x:v[x]for x in ['solved_short','retained_long','conditional_retention']}for k,v in row['contexts'].items()}}


def paired(baseline,candidate,tasks,level):
    before={r['id']:r['pass']for r in baseline['metrics'][f'level{level}']['program']['details']}
    after={r['id']:r['pass']for r in candidate['metrics'][f'level{level}']['program']['details']}
    groups=collections.defaultdict(list)
    for identity,a in before.items():groups[tasks[identity]['story_seed']].append(int(after[identity])-int(a))
    clusters=list(groups.values());rng=random.Random(6116041+level);samples=[]
    for _ in range(10000):
        selected=[rng.choice(clusters)for _ in clusters]
        samples.append(sum(sum(x)for x in selected)/sum(len(x)for x in selected))
    samples.sort();delta=sum(int(after[k])-int(v)for k,v in before.items())/len(before)
    return {'delta':delta,'cluster_bootstrap_95':[samples[250],samples[9749]],'clusters':len(clusters),
      'cluster_unit':'whole story seed, combining all three question families',
      'wins':sum(not v and after[k]for k,v in before.items()),'losses':sum(v and not after[k]for k,v in before.items())}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root.resolve()
    reports={p.stem:json.loads(p.read_text())for p in(root/'results').glob('*.json')}
    selection=json.loads((root/'preselected.json').read_text());chosen=selection['primary_selected_arm']+'-best'
    tasks={t['id']:t for t in read(root/'audit.jsonl')};baseline=reports['baseline'];result={}
    for name,row in reports.items():result[name]={'scores':compact(row),'vs_baseline':{str(k):paired(baseline,row,tasks,k)for k in [1,2,3]},'diagnostics':semantic_diagnostics(row,tasks)}
    training={arm:json.loads((root/arm/'training.json').read_text())for arm in ['direct','auxiliary']}
    assert training['direct']['sample_plan_digest']==training['auxiliary']['sample_plan_digest']
    prepared=json.loads((root/'prepared.json').read_text());manifest=json.loads((root/'export/selected-budget/manifest.json').read_text())
    verification=json.loads((root/'local-verification.json').read_text());native=json.loads((root/'native-verification.json').read_text())
    selected=result[chosen]['scores'];simple_base=compact(baseline)['levels']['1']['program']['rate']
    milestones={'two_operations_50_percent':selected['levels']['2']['program']['rate']>=.5,
      'three_operations_25_percent':selected['levels']['3']['program']['rate']>=.25,
      'simple_drop_at_most_3_percentage_points':selected['levels']['1']['program']['rate']>=simple_base-.03,
      'formal_at_least_95_percent':selected['formal'][0]/selected['formal'][1]>=.95}
    summary={'selected_label':chosen,'selection_used_audit':False,'selected_step':manifest['selected_step'],
      'kept_original_checkpoint':manifest['selected_step']==0,
      'data':{k:prepared[k]for k in ['new_teacher_training_conditions','legacy_replay_conditions','actual_training_errors']},
      'results':result,'milestones':milestones,'all_milestones_met':all(milestones.values()),
      'same_core_sample_plan':True,'sample_plan_digest':training['direct']['sample_plan_digest'],
      'optimizer_updates_each':2000,'core_examples_each':training['direct']['core_examples'],'side_conditions_each':training['direct']['side_conditions'],
      'selected_packed_bytes':manifest['packed_bytes'],'selected_packed_sha256':manifest['packed_sha256'],
      'parameters':manifest['parameters'],'cpu_b200_matches':[verification['cpu_b200_matches'],verification['compared']],
      'fp16_fp32_matches':[verification['fp16_fp32_matches'],verification['compared']],
      'native_matches':{k:[v['native_generations_match'],v['probes']]for k,v in native['models'].items()},
      'audit_conditions':300,'independent_story_seeds':20,'audit_limitations':'Controlled authored tasks; 20 scenarios with repeated question patterns, all four register roles listed including unused inputs; not a broad human benchmark.',
      'physical_picocalc_measured':False,'native_kv_storage':'FP32','auxiliary_Russian_readout_only_used_during_training':True}
    write_json(root/'comparison.json',summary)
    lines=['# 3M HEX: семантика и учебные разборы','',
      f'По валидации до открытия проверки выбран **{chosen}**, шаг **{manifest["selected_step"]}**. Исходный снимок: лучший small-hex из codec-qat-v1, шаг 2000.',
      '', '| Модель | 1 действие /60 | 2 действия /120 | 3 действия /120 | Всего /300 | С инструментами /300 | Формальные /98 |',
      '|---|---:|---:|---:|---:|---:|---:|']
    if manifest['selected_step']==0:
        lines.insert(4,'**Оставлен исходный снимок: ни один дообученный снимок не прошёл правило сохранения простых и формальных задач.**')
        lines.insert(5,'')
    for name in ['baseline','direct-best','auxiliary-best','direct-endpoint','auxiliary-endpoint']:
        score=result[name]['scores'];levels=score['levels']
        lines.append('| '+name+' | '+' | '.join(str(levels[str(k)]['program']['passed'])for k in [1,2,3])+f' | {score["program_total"]} | {score["tools"][0]} | {score["formal"][0]} |')
    lines+=['','Основное сравнение — снимки, выбранные по валидации. Конечные шаги показаны отдельно; по новой проверке снимки не выбирались.',
      '',f'Новый обучающий набор: {prepared["new_teacher_training_conditions"]} условий; повторение прежнего материала: {prepared["legacy_replay_conditions"]}; реальные ошибки исходного студента на обучающих условиях: {prepared["actual_training_errors"]}.',
      'Учитель порождал формулировки по заданному выражению, затем в другом вызове восстанавливал выражение, роли и шаги, видя только условие. Это два вызова одной большой модели, а не независимая человеческая экспертиза. Все эталонные программы проверены на девяти наборах чисел настоящим микрокодовым эмулятором.',
      'Источники разделены между обучением и новой валидацией целиком до порождения перефразировок. Предварительная генерация с пересечением источников отбракована до обновления весов.',
      '', 'Оба студента получили по 2000 обновлений, одинаковые 256000 основных примеров и 64000 дополнительных условий. В direct дополнительные условия обучали компактному разбору; в auxiliary — русским ролям и коротким шагам. Доля дополнительного задания — 20% строк. Полная русская выходная проекция использовалась только для учебного задания и языкового повторения. На исполнении у обеих моделей остались 54 выходных токена, формула и обычный HEX.',
      'Q4 использовался с первого обновления; LR 1e-5, для входных эмбеддингов вдвое меньше, проверка каждые 250 шагов. Разогрева на переводе формул в HEX не было. Выбор сохранял не менее 95% формальных задач и ограничивал падение простых задач на валидации тремя процентными пунктами.',
      '', 'Пик составных задач на новой валидации учителя (диагностика, без учёта ограничения на простые):',
      '', '| Вариант | Шаг | Новые 2 действия /40 | Новые 3 действия /40 | Простые, новые и прежние /40 | Прошёл ограничения |',
      '|---|---:|---:|---:|---:|---|']
    for arm,training_report in training.items():
        peak=max(training_report['history'],key=lambda h:h['key'][1]);s=peak['summary']
        simple=s['new1']['program']['passed']+s['observed1']['program']['passed']
        lines.append(f'| {arm} | {peak["step"]} | {s["new2"]["program"]["passed"]} | {s["new3"]["program"]["passed"]} | {simple} | '+('да'if peak['key'][0]else'нет')+' |')
    lines += [
      '', '## Новая проверка и неопределённость','',
      'В проверке 300 контролируемых русских условий: 20 тематических сюжетов, по три набора вопросов и пять связанных условий. Это не 300 независимых сюжетов и не широкий человеческий экзамен. Интервалы ниже получены парным bootstrap по 20 целым сюжетам, с объединением родственных вопросов.',
      'Во всех условиях перечислены роли четырёх регистров, включая неиспользуемые; нужны привязка словесных ролей к регистрам и выбор нужных входов. Это отдельная проверка переноса, заметно сложнее прежних задач с прямым упоминанием нужных регистров. Новая генерация учителя называла только необходимые входы, поэтому эта проверка дополнительно выявляет сдвиг формата входа. Сравниваются изменения до/после на одном наборе; проценты прежних 140 задач напрямую с этими 300 не сопоставимы.',
      '', '| Действий | Изменение выбранной модели | 95% интервал |', '|---|---:|---:|']
    for k in [1,2,3]:
        d=result[chosen]['vs_baseline'][str(k)];lo,hi=d['cluster_bootstrap_95']
        lines.append(f'| {k} | {d["delta"]*100:+.1f} п.п. | {lo*100:+.1f}…{hi*100:+.1f} п.п. |')
    lines+=['', 'Ориентиры этого раунда: ≥50% для двух действий, ≥25% для трёх; сохранение простых и формальных задач. Выполнены все: **'+('да'if summary['all_milestones_met']else'нет')+'**. Эти ориентиры сами по себе не означают хорошего качества произвольного программирования.',
      '', 'Дополнительная диагностика после завершения проверки: соответствие самостоятельно предсказанной формулы и HEX. Детерминированный компилятор использован только для этой диагностики; модель генерировала весь HEX сама.',
      '', '| Снимок | Своя формула → HEX, точное совпадение /300 | Своя формула верна по числовым тестам /300 |',
      '|---|---:|---:|']
    for name in ['baseline','direct-endpoint','auxiliary-endpoint']:
        diagnostic=result[name]['diagnostics']['counts'];lines.append(f'| {name} | {diagnostic.get("self_calc_to_hex_exact",0)} | {diagnostic.get("self_calc_correct_numeric",0)} |')
    lines += [
      '', '## Контекст и формат','', '| Контекст | Решены в короткой форме | Сохранены в длинной |', '|---|---:|---:|']
    for n,v in selected['long_context'].items():lines.append(f'| {n} | {v["solved_short"]} | {v["retained_long"]} |')
    lines+=['', 'Здесь используются одинаковые задачи в короткой и длинной форме; удержание считается только среди решённых в короткой форме. Посторонние заметки проверяют удержание условия, а не полноценную многоходовую агентную память.',
      '', f'Выбранная модель: **{manifest["parameters"]:,} параметров**, Q4 **{manifest["packed_bytes"]:,} байт**, настроенный контекст 2048. Входной русский словарь и архитектура сохранены; неиспользуемые 32 добавленные строки прежнего опыта не удалялись.',
      f'Точные Q4-пакеты всех пяти результатов повторно загружены; полезные данные повторного экспорта совпадают. CPU/B200: {verification["cpu_b200_matches"]}/{verification["compared"]}; хранение KV в FP16/FP32: {verification["fp16_fp32_matches"]}/{verification["compared"]}.',
      'Пакеты MKA трёх основных моделей проверены на частной копии нативного C++ runtime; исходники продукта не менялись. Реальный PicoCalc не измерялся. Нативная проверка пока использует KV в FP32; проверка FP16 сделана на хосте и не означает внедрение FP16 на устройство.',
      'При 2048 токенах нативный FP32 KV этой 3M занимает 10 МиБ и не помещается в 8 МиБ памяти. Поэтому отдельно подготовлен и проверен пакет `model-context1024.mka`: те же веса, контекст 1024 и KV 5 МиБ. Для контекста 2048 на плате потребуется другой способ хранения KV, например FP16; физическая память и скорость на устройстве ещё не измерялись.',
      '', '## Артефакты','',
      f'- Выбранный Q4: `{root}/export/selected-budget/model.mkqb`',
      f'- Нативный MKA: `{root}/export/selected-budget/model.mka`',
      f'- MKA с контекстом 1024 для текущего FP32 KV: `{root}/export/selected-budget/model-context1024.mka`',
      f'- Мастера весов: `{root}/export/selected-budget/hf/`',
      f'- Все оценки и интервалы: `{root}/comparison.json`',
      f'- Привязка снимков к проверенным пакетам: `{root}/preselected.json`, `final-export.json`.',
      '', f'SHA256 выбранного Q4: `{manifest["packed_sha256"]}`.']
    report=Path(__file__).with_name('SEMANTIC_3M_RESULTS.md');report.write_text('\n'.join(lines)+'\n')
    state_path=Path(__file__).with_name('work-state.json');state=json.loads(state_path.read_text())
    previously_counted=state.get('semantic_3m_v1',{}).get('completed',False)
    state['phase']='semantic_3m_v1_complete';state['all_own_jobs_complete']=True;state['free_language_coding_target_met']=False
    state['semantic_3m_v1']={k:summary[k]for k in ['selected_label','selected_step','data','milestones','all_milestones_met','selected_packed_sha256','parameters','optimizer_updates_each','same_core_sample_plan']}
    state['semantic_3m_v1']['report']=str(report);state['semantic_3m_v1']['artifact']=str(root/'export/selected-budget/model.mkqb')
    state['semantic_3m_v1']['completed']=True
    if not previously_counted:
        state['completed_training_runs']=state.get('completed_training_runs',0)+2
        state['total_accounted_optimizer_updates_lower_bound']=state.get('total_accounted_optimizer_updates_lower_bound',0)+4000
    write_json(state_path,state)
    print(json.dumps({'selected':chosen,'scores':selected,'milestones':milestones,'report':str(report)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
