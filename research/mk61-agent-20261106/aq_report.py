"""Report actual repairs, false completions and the matched prompt ablation."""
import argparse
import json
from pathlib import Path
from aq_common import HERE,ARMS,read,write
from aq_eval import key,brief,summarize


def transitions(before,after):
    a={r['id']:r for r in before['details']};b={r['id']:r for r in after['details']};assert set(a)==set(b)
    return {'gained_success':sum(not a[i]['pass']and b[i]['pass']for i in a),
      'lost_success':sum(a[i]['pass']and not b[i]['pass']for i in a),
      'new_false_DONE':sum(not(a[i]['finished']and not a[i]['program_correct'])and b[i]['finished']and not b[i]['program_correct']for i in a),
      'removed_false_DONE':sum(a[i]['finished']and not a[i]['program_correct']and not(b[i]['finished']and not b[i]['program_correct'])for i in a)}


def extras(panel):
    rows=panel['details'];done=[r for r in rows if r['finished']]
    return {'wrong_fraction_of_DONE':sum(not r['program_correct']for r in done)/len(done)if done else None,
      'premature_DONE_correct_code':sum(r['finished']and r['program_correct']and not r['eligible']for r in rows),
      'mean_agent_turns':sum(len(r['history'])for r in rows)/len(rows),
      'mean_input_tokens':sum(h['generation'].get('input_tokens',0)for r in rows for h in r['history']if'generation'in h)/max(1,sum('generation'in h for r in rows for h in r['history']))}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);root=ap.parse_args().root.resolve()
    load=lambda name:json.loads((root/name).read_text())
    frozen=load('data-frozen.json');prepared=load('prepared.json');pre=load('preselected.json');native=load('native-verification.json');post=load('postflight.json')
    assert native['complete']and not post['own_running_containers']and not pre['fresh_used_for_selection']
    reports={a:load(a+'/fresh.json')for a in ARMS};initial={a:load('initial-full-fresh.json')for a in ARMS}
    training={a:load(a+'/training.json')for a in ARMS}
    assert training['full']['same_draw_digest']==training['short']['same_draw_digest']
    assert training['full']['starting_checkpoint_sha256']==training['short']['starting_checkpoint_sha256']
    selected=pre['selected_arm'];eligible=bool(key(reports[selected])[0]);updates=sum(t['steps']for t in training.values())
    lines=['# Пошаговая отладка и сокращение промпта: 3M Q4','',
      f'По контролю знакомых и незнакомых сочетаний выбрана ветка **{selected}**. '+
      ('Она прошла объявленные исследовательские пороги нового экзамена.'if eligible else'Она пока не прошла объявленные исследовательские пороги нового экзамена.'),
      'Основной профиль генератора и прошивка не заменялись.','',
      f'Подготовлено {prepared["total_course_rows"]:,} учебных шагов на {frozen["group_counts"]["train"]} учебных условиях прежнего прогона; '
      f'{prepared["common_valid_lessons"]:,} шагов помещаются в оба формата. '
      f'Из обеих веток исключены {sum(prepared["dropped_for_both_arms"].values())} слишком длинных примера. '
      f'На каждой B200 выполнено по {training["full"]["steps"]} шагов, всего {updates} обновлений.','',
      'В первом прогоне обнаружено несовпадение бюджета учебного старта и реальной сессии (10 против 12); контроль подтвердил зависимость от числа. Исходный прогон сохранён и учтён. Новый учитель создаёт состояния через живую Session, включая одинаковые истории для правильного и неверного кода. Обе ветки заново начинают с одного сохранённого чекпойнта выпущенной AJ lr10-terminal 3M HEX. '
      'Совпадают случайные выборки, оптимизатор, расписание, число обновлений и учитель; меняется только формат входа. '
      'Свежие адаптеры rank16 обучают внимание и MLP, а также строки действий и корректности. '
      f'Всего {prepared["trainable_parameters"]:,} обучаемых коэффициентов; после слияния остаётся 3 022 080 параметров. '
      'Во всех прямых проходах используется реальная сетка Q4, обучение ведётся в FP32.','',
      'Учебные цели: составить HEX по условию; выдать локализованный диагноз; исправить программу после диагноза; '
      'продолжить после неудачной правки или ложного прежнего диагноза; запустить недостающие публичные случаи; '
      'завершить правильный проверенный код. Исправление неверного кода получает больший вес на изменённых токенах. '
      'Правильные программы включены как самостоятельные положительные примеры.','',
      'DIAG имеет пять байтов `TT HH LL AA BB`: тип ошибки, индекс в текущем HEX, текущий и предлагаемый байты. '
      '00 означает правильный код, 01 — операцию, 02 — аргумент, 03 — порядок; правильный диагноз имеет вид `00 FF FF 00 00`. '
      'Диагноз является гипотезой сети. Harness показывает только реальный текущий байт и факты эмулятора. '
      'Он не сообщает, верен ли предложенный байт, и не блокирует DONE по скрытой проверке.','',
      'Учитель целей и диагнозов — живые Session, компилятор эталонов и настоящий ROM; бюджеты вычисляются из реальных историй действий. Большая LLM не вызывалась. '
      'Дополнительно замороженная исходная сеть получает полный вход; её распределения копируются только там, '
      'где предсказанное действие или токен совпадают с проверенной учебной целью. '
      'Это сочетание обучения по эталону и ограниченной дистилляции контекста, а не чистое копирование текущей слабой сети.','',
      f'Новый экзамен: {frozen["episode_counts"]["fresh"]} состояний знакомых семейств и '
      f'{frozen["episode_counts"]["novel-fresh"]} состояний с удержанными сочетаниями операций. '
      'Вопросы нового экзамена не встречались в AP и текущем обучении/контроле; исторические совпадения с более ранним AO отмечены отдельно. '
      'Незнакомые пары исключены из текущего обучения; это не утверждение об отсутствии их во всей истории предобучения. '
      'Для половины групп в исходном состоянии имеется заведомо неверный прежний диагноз, одинаковый у обеих веток. '
      'Экзамен содержит по одному правильному кандидату и по три вида ошибки на каждое условие.','',
      'Успех — правильный итоговый код на трёх публичных и трёх скрытых случаях, все публичные исполнения '
      'для последней версии и собственный DONE модели в бюджете 12 действий. '
      'Начальные факты трёх запусков предоставляются одинаково для всех готовых кандидатов. '
      'После WRITE прежние результаты аннулируются. Эталон и ожидаемые состояния используются только офлайн.','',
      '| Q4, новые эпизоды | Решено | Ложных DONE | Правильные старты завершены | Правильные старты испорчены | Ошибки генерации |',
      '|---|---:|---:|---:|---:|---:|']
    terminals={a+'-terminal':load(a+'/terminal-fresh.json')for a in ARMS if(root/a/'terminal-fresh.json').exists()}
    all_reports={'source-full':initial['full'],**reports,**terminals};metrics={};paired={};patterns={};cohorts={}
    for name,report in all_reports.items():
        metrics[name]={}
        for panel in ['known','novel','scratch']:
            r=report[panel];ex=extras(r);metrics[name][panel]={**{k:v for k,v in r.items()if k not in ['details','by_family']},**ex}
            good=f'{r["correct_starts_completed"]}/{r["correct_starts"]}'if r['correct_starts']else'—'
            lines.append(f'| {name}, {panel} | {r["passed"]}/{r["total"]} ({r["passed"]/r["total"]:.1%}) | '
              f'{r["false_DONE"]} ({r["false_DONE"]/r["total"]:.1%}) | {good} | {r["correct_starts_corrupted"]} | {r["generation_errors"]} |')
    lines+=['','`source-full` — общая исходная модель в полном шестикомандном harness до этого обучения. '
      'Это не переоценка старого пятикомандного профиля в его прежнем интерфейсе. '
      'Состояния scratch начинаются без программы и фактов её исполнения; это отдельные 32 условия, '
      'которые также входят в известные семейства, поэтому их нельзя складывать с основными эпизодами как независимые задачи.','',
      '| Выдача DONE | Всего DONE | Доля неверного кода среди DONE | Правильный код, но не все случаи проверены |',
      '|---|---:|---:|---:|']
    if terminals:
        lines=lines[:-2]
        lines+=['','Профили `full-terminal` и `short-terminal` — дополнительная проверка после одинаковых 2500 шагов. '
          'Эта проверка объявлена до обучения и открытия нового экзамена. '
          'Конечный шаг взят из заранее фиксированного бюджета, а не подбирался по экзамену. '
          'Эта дополнительная диагностика не меняет предварительно выбранные ветку и чекпойнт.','',
          '| Выдача DONE | Всего DONE | Доля неверного кода среди DONE | Правильный код, но не все случаи проверены |',
          '|---|---:|---:|---:|']
    for arm in ARMS:
        for panel in ['known','novel','scratch']:
            m=metrics[arm][panel];fraction=m['wrong_fraction_of_DONE']
            lines.append(f'| {arm}, {panel} | {m["all_DONE"]} | '+(f'{fraction:.1%}'if fraction is not None else'—')+f' | {m["premature_DONE_correct_code"]} |')
    lines+=['','| Прямой запрос DIAG | Верный тип | Тип, индекс и оба байта верны |','|---|---:|---:|']
    for name,report in all_reports.items():
        for panel,r in report['diagnosis'].items():
            lines.append(f'| {name}, {panel} | {r["class_correct"]}/{r["total"]} | {r["localized_exact"]}/{r["total"]} |')
    lines+=['','Отдельно проверены исходные состояния без прежнего диагноза и стресс-состояния с ним. '
      'В стресс-состояниях старый диагноз всегда заведомо неверен; эта панель не является случайной смесью верных и неверных подсказок. '
      'Её нельзя использовать отдельно как доказательство общей проверки смысла. Чистая панель не содержит такой подсказки.','',
      '| Q4, исходное состояние | Ветка / панель | Решено | Ложных DONE |','|---|---|---:|---:|']
    for name,report in all_reports.items():
        cohorts[name]={}
        for panel in ['known','novel']:
            cohorts[name][panel]={}
            for cohort,has_claim in [('plain',False),('previous_false_claim',True)]:
                rows=[]
                for row in report[panel]['details']:
                    first=next((h.get('prompt','')for h in row['history']if'prompt'in h),'')
                    if ('Диагноз сети, версия 1:'in first)==has_claim:rows.append(row)
                m=summarize(rows);cohorts[name][panel][cohort]={k:v for k,v in m.items()if k!='details'}
                lines.append(f'| {cohort} | {name}, {panel} | {m["passed"]}/{m["total"]} | {m["false_DONE"]} |')
    lines+=['','Диагностические пробы принудительно запрашивают DIAG и не подсказывают диагноз агенту в основных эпизодах. '
      'При нескольких допустимых местах исправления точное совпадение с одним эталонным диагнозом строже семантической корректности. '
      'Качество свободных исправлений оценивается исполнением, а не совпадением байтов с эталоном.','',
      '| Контроль Q4 | Шаг | Знакомые: решено / ложных DONE | Новые пары: решено / ложных DONE | Минимальная полезность |','|---|---:|---:|---:|---:|']
    policy=load('policy.json')
    for arm in ARMS:
        for step in policy['checkpoints']:
            r=load(f'{arm}/development-{step}.json');k=key(r)
            lines.append(f'| {arm} | {step} | {r["known"]["passed"]}/{r["known"]["total"]}; {r["known"]["false_DONE"]} | '
              f'{r["novel"]["passed"]}/{r["novel"]["total"]}; {r["novel"]["false_DONE"]} | {k[1]:.3f} |')
    lines+=['','Контроль на шаге 500 считается прогревом и не участвует в отборе; допустимы только шаги 1250 и 2500. Отбор сначала проверяет пороги на обеих контрольных панелях, затем максимизирует худшую из '
      'полезностей `(успех − 4×ложные DONE)/эпизоды`. Пороги: успех не ниже 80%, ложных DONE не более 5% эпизодов, '
      'правильных стартов завершено не меньше 80%. Экзамен не меняет чекпойнт или выбранную ветку.','',
      '| Семейство | Ветка | Решено на known | Ложных DONE |','|---|---|---:|---:|']
    for arm in ARMS:
        for family,m in reports[arm]['known']['by_family'].items():
            lines.append(f'| {family} | {arm} | {m["passed"]}/{m["total"]} | {m["false_DONE"]} |')
    for arm in ARMS:
        paired[arm]={n:transitions(initial[arm][n],reports[arm][n])for n in ['known','novel','scratch']}
        patterns[arm]={}
        for panel in ['known','novel','scratch']:
            wrong=[r for r in reports[arm][panel]['details']if r['finished']and not r['program_correct']]
            patterns[arm][panel]={'false_DONE':len(wrong),
              'false_DONE_after_own_write':sum(any(h.get('generation',{}).get('action')=='write'for h in r['history'])for r in wrong),
              'false_DONE_after_own_write_and_all_public_runs':sum(r['eligible']and any(h.get('generation',{}).get('action')=='write'for h in r['history'])for r in wrong)}
        bad=[];lost=[]
        for panel in ['known','novel','scratch']:
            base={r['id']:r for r in initial[arm][panel]['details']}
            for r in reports[arm][panel]['details']:
                if r['finished']and not r['program_correct']:bad.append({'panel':panel,'episode':r,'baseline':base[r['id']]})
                if base[r['id']]['pass']and not r['pass']:lost.append({'panel':panel,'episode':r,'baseline':base[r['id']]})
        for suffix,rows in [('false-DONE',bad),('lost-success',lost)]:
            p=root/f'{arm}-{suffix}.jsonl';p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows));lines+=['',f'[{arm}: {suffix}, {len(rows)} примеров]({p}).']
    write(root/'trajectory-patterns.json',patterns)
    lines+=['','| Повторная проверка неверной правки | Ложных DONE | Из них после собственного WRITE и всех публичных запусков |',
      '|---|---:|---:|']
    for arm,panels in patterns.items():
        for panel,p in panels.items():lines.append(f'| {arm}, {panel} | {p["false_DONE"]} | {p["false_DONE_after_own_write_and_all_public_runs"]} |')
    lines+=['','Завершение после всех запусков неверной правки показывает, что соблюдение последовательности инструментов '
      'не гарантирует проверки смысла результата. Эти случаи сохраняются как ошибки; скрытый проверяющий не блокировал DONE.']
    history=json.loads((root.parent/'history-overlap.json').read_text());new_only={}
    lines+=['','До просмотра ответов нового экзамена найдены 5 совпадений текста/режима с более ранним AO '
      '(20 состояний основной панели); с AP совпадений нет. Дополнительно показаны только вопросы без таких совпадений.','',
      '| Вопросы без исторических совпадений | Решено | Ложных DONE |','|---|---:|---:|']
    for name,report in all_reports.items():
        new_only[name]={}
        for panel,file in [('known','fresh'),('novel','novel-fresh')]:
            excluded=set(history['excluded_ids'][file]);rows=[r for r in report[panel]['details']if r['task_id']not in excluded]
            m=summarize(rows);new_only[name][panel]={k:v for k,v in m.items()if k!='details'}
            lines.append(f'| {name}, {panel} | {m["passed"]}/{m["total"]} | {m["false_DONE"]} |')
    budget=load('prompt-budget.json');saved=budget['saved_min_median_max'][1]
    lines+=['','Сокращение постоянного текста','',
      f'В учебных состояниях медиана полного входа {budget["full_min_median_max"][1]:g} токенов, '
      f'короткого — {budget["short_min_median_max"][1]:g}; медианная экономия {saved:g}. '
      'В новой версии полная инструкция длиннее прежней из-за описания DIAG, поэтому выигрыш отличается от старых 268 токенов. '
      'Динамические режим углов, условие, константы, HEX, факты и прежний диагноз сохраняются в обоих форматах. '
      'В текущем опыте обе модели используют окно 1024 и одинаковый размер KV. Сокращение входа само по себе не уменьшило '
      'выделенный буфер; освобождены позиции для полезного состояния.','',
      'Нативная проверка','']
    for arm,m in native['models'].items():
        lines.append(f'- {arm}: точное совпадение потоков действий и HEX CPU/B200 и C++/B200 на {m["probes"]}/{m["probes"]} пробах; '
          f'MKA {m["package_bytes"]:,} байт; KV {m["cache_bytes"]:,} байт; окно 1024. '
          f'Максимальная разница оценок корректности {max(r["margin_error"]for r in m["details"]):.6f}.')
    lines+=['- Входной русский словарь и неадаптируемые тензоры побитово сохранены. '
      'SHA данных, исходных весов и замороженных исходников проверены; все собственные GPU-задания завершены.',
      '- Используется прежний переносимый C++ движок и грамматика HEX; DIAG занимает существующий служебный токен. '
      'Физический PicoCalc не измерялся, прошивка не менялась.','',
      'Границы: короткие арифметические программы, регистры, константы, простые составные выражения; одна исходная ошибка. '
      'Циклы, длинные игры и несколько одновременно внесённых дефектов не покрыты этим новым экзаменом. '
      'Выдача структурированного диагноза не доказывает способность к общим рассуждениям.','',
      f'[Полный Q4]({root/"export/full/model.mka"}); [короткий Q4]({root/"export/short/model.mka"}); '
      f'[проверка C++]({root/"native-verification.json"}).']
    sensitivity=load('budget-sensitivity.json')if(root/'budget-sensitivity.json').exists()else None
    if sensitivity:
        lines+=['','Контроль прежнего случайного признака: выбор WRITE для пустой программы при изменении только бюджета.',
          '','| Конечный Q4 | Бюджет 10 | Бюджет 12 |','|---|---:|---:|']
        for arm,v in sensitivity['terminal_profiles'].items():
            lines.append(f'| {arm} | {v["10"]["write_actions"]}/{v["10"]["total"]} | {v["12"]["write_actions"]}/{v["12"]["total"]} |')
        lines+=['','Это отдельная контрольная проба первого действия, а не оценка правильности построенной программы. '
          'Она не использовалась для отбора чекпойнта.']
    path=HERE/'STEP_DEBUG_V2_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    summary={'completed':True,'selected_arm':selected,'selected_step':pre['choices'][selected]['step'],
      'research_thresholds_passed':eligible,'main_actor_changed':False,'optimizer_updates':updates,
      'metrics':metrics,'cohorts':cohorts,'new_question_only':new_only,'history_overlap':history,'paired_transitions':paired,'trajectory_patterns':patterns,'prompt_budget':budget,'native_verified':True,
      'additional_fixed_endpoint_comparison':bool(terminals),'endpoint_not_used_for_selection':bool(terminals),
      'budget_sensitivity':sensitivity,
      'fresh_used_for_selection':False,'physical_device_measured':False}
    write(root/'summary.json',summary);state=json.loads((HERE/'work-state.json').read_text())
    if not state.get('step_debug_v2',{}).get('completed'):
        state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=updates
    state.update(phase='step_debug_v2_complete',active_experiment=None,all_own_jobs_complete=True,latest_report=str(path),
      next_action='Review actual repair/DONE errors and full/short prompt comparison; no firmware deployment requested.')
    state['step_debug_v2']={'completed':True,'root':str(root),'report':str(path),'summary':summary};write(HERE/'work-state.json',state)
    print(json.dumps({'completed':True,'report':str(path),'selected':selected,'thresholds_passed':eligible}),flush=True)


if __name__=='__main__':main()
