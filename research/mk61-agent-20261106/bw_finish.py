"""Report the isolated phase effects and the preselected route's fresh audit."""
import time
import numpy as np
from bw_common import ROOT,HERE,ROUTES,read,write,rows,sha,check_frozen
from bw_eval import select,paired_primary_checks,composition_count,brief
from br_finish import paired
from be_language import paths3

CONTRASTS={'new_replan_given_U_initial':('UU','UN'),'new_replan_given_N_initial':('NU','NN'),
    'new_initial_given_U_replan':('UU','NU'),'new_initial_given_N_replan':('UN','NN')}


def family_ci(left,right):
    held={tuple(v)for v in read(ROOT/'ast-frozen.json')['held_triples']['closed']}
    goals={g['id']:g for g in rows(ROOT/'closed.jsonl')if g['family']=='composition'}
    index={k:i for i,k in enumerate(sorted(held))};d=np.zeros((len(index),3))
    a={r['id']:r for r in left['own']['records']if r['family']=='composition'}
    b={r['id']:r for r in right['own']['records']if r['family']=='composition'}
    for k,x in a.items():
        y=b[k];keys=paths3(goals[x['task_id']]['spec']['X'])&held;assert len(keys)==1;j=index[next(iter(keys))]
        d[j,0]+=int(y['pass'])-int(x['pass'])
        if not x['initially_correct']:d[j,1]+=int(y['pass'])-int(x['pass'])
        d[j,2]+=int(y['finished']and not y['program_correct'])-int(x['finished']and not x['program_correct'])
    den=np.array([320,160,320]);rng=np.random.default_rng(261125129);sample=rng.integers(0,len(d),(10000,len(d)))
    boot=d[sample].sum(1)/den*100;point=d.sum(0)/den*100
    return {k:{'delta_percentage_points':float(point[i]),'CI95_family_bootstrap':[float(v)for v in np.percentile(boot[:,i],[2.5,97.5])]}
        for i,k in enumerate(['completion','repairs','accepted_false_DONE'])}


def table(reports,goals,composition_goals):
    lines=[f'| Первый перевод / повторный | SPEC /{goals} | Композиции /{composition_goals} | Завершено /{2*goals} | Исправлено /{goals} | Верный код доведён /{goals} | Порча | Принятые ложные DONE |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for route,r in reports.items():
        s=r['own']['summary'];lines.append(f"| {route[0]}/{route[1]} | {r['primary']['summary']['passed']} | {composition_count(r)} | {s['passed']} | {s['wrong_starts_repaired']} | {s['correct_starts_completed']} | {s['correct_starts_corrupted']} | {s['false_DONE']} |")
    return lines


def protections(report,parent):
    x=select({'UU':parent,'candidate':report})['decisions']['candidate']
    return x['checks']


def main():
    check_frozen();root=ROOT/'server-results';done=read(root/'complete.json');native=read(root/'native-verification.json')
    assert done['all_model_parameters_unchanged']and done['optimizer_updates']==0
    assert read(root/'controller-complete.json')['all_own_workers_joined']and native['complete']
    assert read(root/'postflight.json')['Qwen_health']=='200'
    dev={r:read(root/('development-'+r+'.json'))for r in ROUTES}
    closed={r:read(root/('closed-'+r+'.json'))for r in ROUTES}
    assert paired_primary_checks(dev)and paired_primary_checks(closed)
    for reports in [dev,closed]:
        # The forced-wrong-SPEC panel never calls the initial translator.
        for left,right in [('UU','NU'),('UN','NN')]:
            assert reports[left]['wrong']['summary']==reports[right]['wrong']['summary']
            assert reports[left]['wrong']['replan']==reports[right]['wrong']['replan']
    before=select(dev);choice=read(root/'preselected.json')
    for k in before:assert before[k]==choice[k]
    chosen=choice['chosen'];checks=protections(closed[chosen],closed['UU'])
    uncertainty={name:paired(closed[a]['own']['records'],closed[b]['own']['records'])for name,(a,b)in CONTRASTS.items()}
    families={name:family_ci(closed[a],closed[b])for name,(a,b)in CONTRASTS.items()}
    chosen_uncertainty=paired(closed['UU']['own']['records'],closed[chosen]['own']['records'])
    report=HERE/'SPEC_PHASE_ROUTING_RESULTS.md'
    selected=closed[chosen]['own']['summary'];baseline=closed['UU']['own']['summary']
    winner=('Ни один другой маршрут не прошёл весь заранее заданный отбор; выбран U/U.'if chosen=='UU'else
        f'До просмотра закрытого теста выбран маршрут {chosen[0]}/{chosen[1]}.')
    confirmed=chosen!='UU'and all(checks.values())and selected['passed']>baseline['passed']
    verdict=('На этом новом закрытом наборе выбранный маршрут сохранил все заданные метрики и улучшил завершения.'if confirmed else
        'Общее преимущество нового маршрута на новом закрытом наборе не подтверждено.')
    lines=['# Раздельный выбор первого и повторного перевода SPEC','',winner+' '+verdict,'',
        'U — прежний переводчик BU1500; N — адаптер после восстановления, BU1500 +2400 обновлений. Первая буква — первоначальный перевод, вторая — повторный разбор условия. Во всех четырёх сочетаниях обычные действия и тела WRITE выдаёт один и тот же исходный actor. Новых шагов обучения не было; все веса сохранены побитно.','',
        '## Новый закрытый тест в Q4','',*table(closed,256,160),'',
        '256 новых условий, 512 обычных эпизодов и 64 стресс-эпизода с намеренно неверной SPEC. Композиции — 32 новые тройки операций по5 условий. Четыре сочетания проверены на одинаковых программах и входах. Выбор маршрута завершён до первого ответа моделей на closed; после просмотра теста не менялся.','',
        '## Повторный разбор','',
        'Верность здесь вычислена только для отчёта по отложенным числовым входам. Ни эталон, ни истинность SPEC не доступны маршрутизатору. Для эпизодов, где повторный разбор состоялся, сравниваются первоначальная и конечная гипотезы; неверная включает недоступную SPEC. Число таких эпизодов зависит от поведения агента; доли среди них нельзя прямо сравнивать как одинаковую случайную выборку.','',
        '| Маршрут | Повторных разборов | Верная → неверная SPEC | Неверная → верная | Верная → верная | Неверная → неверная |',
        '|---|---:|---:|---:|---:|---:|']
    for route,r in closed.items():
        s=r['own']['replan'];lines.append(f"| {route[0]}/{route[1]} | {s['replanned']} | {s['correct_to_wrong']} | {s['wrong_to_correct']} | {s['correct_to_correct']} | {s['wrong_to_wrong']} |")
    lines+=['','| Маршрут | Эпизоды с ложными заявлениями DONE | Все ложные заявления | Переполнения | UNSURE | Стресс: ложные DONE /64 | Ошибки формата SPEC /256 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for route,r in closed.items():
        s=r['own']['summary'];lines.append(f"| {route[0]}/{route[1]} | {s['episodes_with_false_DONE_claims']} | {s['false_DONE_claims']} | {s['context_overflows']} | {s['abstained']} | {r['wrong']['summary']['false_DONE']} | {r['primary']['summary']['codec_errors']} |")
    lines+=['','Принятые ложные DONE отделены от отклонённых ложных заявлений. Порча считается после предусмотренного механического отката незавершённых изменений. Проверка относительно заявленной SPEC не доказывает, что русское условие понято верно, и конечные числовые тесты не доказывают корректность на всех входах.','',
        '## Отбор на development','',*table(dev,64,40),'',
        'Использованы64 условия прежнего development, на котором до этого был проверен только U/U. Прежний закрытый набор BV не использовался для отбора: из него взяты только2 снятых с роли теста диагностических примера с известными ошибками повторного разбора.','',
        'Допускаются только маршруты без ухудшения первого перевода, композиций, завершений, исправлений, доведения верного кода, принятых ложных DONE, порчи, эпизодов с ложными заявлениями и ложных DONE в стресс-проверке относительно U/U. Среди них приоритет — завершения, исправления, доведение верного кода; при равенстве предпочитается U/U, затем N/U.','',
        'Непройденные критерии: `'+str({route:[k for k,v in x['checks'].items()if not v]for route,x in choice['decisions'].items()})+'`. Выбран `'+chosen+'`. Проверка тех же защит на новом closed: `'+str(checks)+'`. Это проверка заранее выбранного решения, а не повторный отбор.','',
        '## Изолированные эффекты фаз','',
        'Здесь меняется одна фаза при неизменной другой. Положительная разница завершений означает преимущество второго маршрута пары; для ложных DONE желательна отрицательная разница.10000 попарных bootstrap-выборок по256 условиям; оба начальных состояния условия остаются вместе. Это неопределённость по задачам одного набора, не оценка повторных обучений.','',
        '| Сравнение | Завершения, п.п. [95% ДИ] | Исправления, п.п. [95% ДИ] | Ложные DONE, п.п. [95% ДИ] |',
        '|---|---:|---:|---:|']
    for name,(a,b)in CONTRASTS.items():
        cells=[]
        for metric in ['completion','repairs','accepted_false_DONE']:
            v=uncertainty[name][metric];lo,hi=v['CI95_task_bootstrap'];cells.append(f"{v['delta_percentage_points']:+.2f} [{lo:+.2f}; {hi:+.2f}]")
        lines.append('| '+b+' минус '+a+' | '+' | '.join(cells)+' |')
    lines+=['','Отдельные интервалы по32 семействам композиций сохранены в `comparison.json`; все5 условий семейства и оба старта остаются в одной группе. Большое число метрик и сравнений не превращает небольшой перевес в подтверждённое общее улучшение.','',
        '## Диагностические примеры и сохранённые навыки','',
        '| Маршрут | Два прежних условия: завершено /4 | Повторный разбор: верная → неверная |',
        '|---|---:|---:|']
    for route in ROUTES:
        r=read(root/('diagnostic-'+route+'.json'));lines.append(f"| {route[0]}/{route[1]} | {r['own']['summary']['passed']} | {r['own']['replan']['correct_to_wrong']} |")
    known=read(ROOT/'known-fit.json')
    lines+=['','Эти2 условия — `10^R6 → RD` и `log10(RB) → R4`. Они уже были разобраны и не являются новым тестом. Их роль — проверить воспроизводимость механизма ошибки и правильность переключения фаз.','',
        'Известные учебные контроли зависят от первого переводчика: у U исправлено0/9 прежних потерь, у N9/9 плюс отдельный косинус. Старые переводы: U102/128, N116/128 с одной потерей прежнего успеха. Старые композиции: U185/240, N195/240 без потери прежних185 успехов. Это результаты прежних фиксированных весов на уже известных контролях, не новые независимые достижения.','',
        '## Реализация и ограничения','',
        'Маршрутизация определяется явной фазой вызова. Текст условия, числа, эталонная SPEC и результат проверки верности не выбирают модель. Все обычные вызовы, включая обычный WRITE, идут исходному actor. Для U/U и U/N первоначальные потоки токенов совпадают; для N/U и N/N тоже. U/U точно воспроизвёл все прежние метрики development.','',
        'В стресс-панели начальная SPEC задана извне, поэтому замена только первого переводчика не должна влиять на результат. Совпадение U/U с N/U и U/N с N/N проверено отдельно. Первый запуск остановился до инференса из-за различия служебного manifest actor; веса и токенизатор совпадали. Сделана отдельная копия actor для опыта, данные и политика остались прежними; аудит сохранён в `pre-inference-repair.json`.','',
        'Кэширование использует неизменный профиль, полный промпт и принудительный тип действия. Оно не меняет ответы, число действий или окно контекста. Численная проверка, rollback, лимит12 действий, контекст1024 и FP32 KV прежние.','',
        'Новый closed был зафиксирован до оценки. DeepSeek-V4.1-Flash формулировал условия и дважды восстанавливал их смысл без исходного AST. Это одна большая модель, а не независимая человеческая разметка. Все выбранные AST сохранены. Код и числовые проверки выполнены ROM-эмулятором. Отложенные тройки операций и числа проверены против известных прежних целей и наблюдавшихся гипотез.','',
        f"Нативно проверены {native['streams_verified']} совпадающих потоков B200/CPU/C++. Повторно использованы неизменные ранее проверенные Q4-пакеты. Переключение выполнялось в одном буфере весов {native['one_weight_buffer_bytes']} байт; KV {native['KV_bytes']} байт, workspace {native['workspace_bytes']} байт. Смешанному маршруту N/U или U/N нужны3 хранимых профиля, однородному U/U или N/N —2, включая actor. Это дополнительное хранение и загрузка, физическая скорость PicoCalc не измерялась.",'',
        f"Один ограниченный worker на B200 рядом с Qwen, allocator≤1536МиБ, целевая доля активного времени0.5. Пик reserved PyTorch {done['peak_reserved_MiB']:.1f}МиБ без контекста CUDA и внешних библиотек. После работы /health Qwen200, собственный worker остановлен. Обучений и новых optimizer updates:0. Рабочая модель приложения не заменялась.",'',
        'Область оценки — прямолинейные арифметические выражения с записью результата в память. Вывод не распространяется на произвольные ветвления и циклы игр МК-61.','',
        'Артефакты: `.build/mk61-agent-20261106/spec-phase-routing-v1`; `server-results/preselected.json`, `development-*.json`, `closed-*.json`, `native-verification.json`, `comparison.json`.','']
    report.write_text('\n'.join(lines))
    result={'complete':True,'optimizer_updates':0,'choice':choice,'closed_confirmation':checks,'selected_improvement_confirmed':confirmed,
        'development':{k:brief(v)for k,v in dev.items()},'closed':{k:brief(v)for k,v in closed.items()},
        'isolated_phase_uncertainty':uncertainty,'composition_family_uncertainty':families,'selected_uncertainty':chosen_uncertainty,
        'native_streams':native['streams_verified'],'all_weights_unchanged':True,'report':str(report),'postprocessor_sha256':sha(__file__)}
    write(ROOT/'comparison.json',result)
    state=read(HERE/'work-state.json');entry=state.get('latest_phase_routing',{})
    entry.update(phase='complete',complete=True,optimizer_updates=0,chosen=chosen,report=str(report),selected_improvement_confirmed=confirmed)
    state.update(latest_phase_routing=entry,phase='spec_phase_routing_complete',active_experiment=None,all_own_jobs_complete=True,
        result_report=str(report),next_action='Use isolated phase results to design the next cumulative-replay and meaning-consistency course.')
    write(HERE/'work-state.json',state)
    write(ROOT/'finish.json',{'complete':True,'optimizer_updates':0,'report_sha256':sha(report),'postprocessor_sha256':sha(__file__),'training_ledger_unchanged':True,'unix':time.time()})
    print({'complete':True,'chosen':chosen,'selected_improvement_confirmed':confirmed,'report':str(report)},flush=True)


if __name__=='__main__':main()
