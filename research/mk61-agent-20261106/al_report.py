"""Summarize the internal semantic-adaptation experiment without exam selection."""
import argparse
import json
import shutil
from pathlib import Path
from al_common import HERE, PARENT, ARMS, read, write
from ak_report import brief, transitions


def load(root, name): return json.loads((root/name).read_text())


def initial_semantics(report):
    result = {}
    for panel, p in report.items():
        records = []
        for r in p['details']:
            h = next((h for h in r['history'] if 'prompt' in h and 'generation' in h), None)
            if h is not None and h['generation'].get('correctness_margin') is not None:
                records.append((h['generation']['correctness_margin'] >= 0, bool(r['initially_correct'])))
        result[panel] = {'correct': sum(a == b for a, b in records), 'total': len(records),
            'false_positive': sum(a and not b for a, b in records), 'false_negative': sum(not a and b for a, b in records)}
    return result


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', type=Path, required=True); root = ap.parse_args().root.resolve()
    pre = load(root, 'preselected.json'); native = load(root, 'native-verification.json'); post = load(root, 'postflight.json')
    assert native['complete'] and not pre['fresh_used_for_selection']
    assert post['all_frozen_data_sources_verified'] and not post['own_running_containers']
    data = load(root, 'data-frozen.json'); prepared = load(root, 'prepared.json'); policy = load(root, 'policy.json')
    initial = load(root, 'initial-fresh.json'); reports = {'source': initial}
    for arm in ARMS:
        for role in ['best', 'research']: reports[arm+('-research' if role == 'research' else '')] = load(root, arm+'/'+role+'-fresh.json')
    coupling = load(root, 'coupling-preselected.json')
    assert not coupling['fresh_used_for_selection']
    for arm in ARMS: reports[arm+'-coupled'] = load(root, arm+'/coupled-fresh.json')
    stats = {n: brief(r) for n, r in reports.items()}
    selected = coupling['selected_arm']+'-coupled'; choice = coupling['choices'][coupling['selected_arm']]
    semantic = {n: initial_semantics(r) for n, r in reports.items()}
    release_policy = load(root.parent, 'release-policy.json')
    assert release_policy['created_before_any_new_exam_inspection']
    heldout_retained = all(p['passed'] >= initial[n]['passed'] and p['false_DONE'] <= initial[n]['false_DONE'] and
        p['correct_controls_completed'] >= initial[n]['correct_controls_completed'] for n, p in reports[selected].items())
    false_improved = sum(p['false_DONE'] for p in reports[selected].values()) < sum(p['false_DONE'] for p in initial.values())
    promoted = choice['step'] > 0 and heldout_retained and false_improved
    lines = ['# 3M Q4: совместное понимание цели, кода и результата', '',
        f'Выбран по новому контролю: **{selected}, шаг {choice["step"]}, β={choice["beta"]}**. '
        f'Новый чекпойнт прошёл условия выпуска после экзамена: **{promoted}**. '
        'Экзамен не использован для выбора весов. Отдельное заранее записанное условие выпуска '
        'требует удержания всех трёх панелей и уменьшения суммарных ложных DONE.', '',
        'Перед прогоном разобраны 62 ложных DONE предыдущего экзамена: 61 программа '
        'неверна уже на открытом случае, одна — только на скрытом. Публичные результаты '
        'сеть видит; эталонные значения на вход не передаются. Эти прежние эпизоды теперь учебные.', '',
        'Предыдущая попытка исправляла только пять линейных векторов действий. Теперь '
        'адаптируются внутренние признаки: `late` — Q/V и три матрицы MLP последних двух '
        'блоков, `all` — те же матрицы всех десяти блоков. Оба профиля начинают с одного '
        'AJ lr10-terminal Q4, свежие LoRA rank16/alpha32 имеют нулевое влияние при старте. '
        'Инициализация общих адаптеров, последовательность учебных выборок и потери одинаковы.', '',
        f'Проверено {data["crossed_groups"]} учебных квадратов, помещаются в обучение '
        f'{prepared["fitting_crossed_groups"]}. Каждый содержит две цели и два кода: '
        'диагональные сочетания правильны, остальные ошибочны. При фиксированном коде '
        'фактические результаты совпадают для обеих целей; оба ошибочных сочетания '
        'проверены на различающий публичный случай. Следовательно, одной частотой DONE '
        'или видом кода выполнить все четыре метки нельзя.', '',
        'Классификация корректности и выбор действия обучаются вместе с четырьмя '
        'сравнениями внутри квадрата: по двум фиксированным целям и двум фиксированным кодам. '
        'Дополнительно учатся полные проверенные исправления WRITE→RUN→DONE, новые обычные '
        'задачи и сохранение прежних ответов. Общего штрафа за любое DONE нет. Для KD '
        'удерживаются только те действия/токены исходного учителя, где его argmax согласен '
        'с проверенной учебной меткой.', '',
        f'Учебных исправляющих шагов {data["hard_lessons"]}, обычных {data["ordinary_lessons"]}, '
        f'удерживающих {data["retention_lessons"]}. Выполнено по {policy["steps"]} обновлений '
        f'на двух B200, всего {2*policy["steps"]}. Контроль каждые 250. Большая LLM в этом '
        'прогоне не вызывалась: учитель составляет исправление по исходной программе, '
        'метки и исполнения проверяются ROM-эмулятором.', '',
        'Входной словарь и формат HEX не изменены. Слияние адаптеров даёт прежние '
        '3 022 080 параметров; Q4 действует в каждом прямом проходе. Runtime не имеет '
        'скрытых тестов/эталонного кода/ожидаемых значений и не запрещает raw-DONE по порогу.', '',
        '| Новый экзамен Q4 | Решено /320 | Ложных DONE | Операции /192 | Ложных DONE | Завершение /96 | Ложных DONE |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name, s in stats.items():
        m, k, c = [s[n] for n in ['main', 'skills', 'completion']]
        lines.append(f'| {name} | {m["passed"]} | {m["false_DONE"]} | {k["passed"]} | {k["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} |')
    lines += ['', '| Новый основной экзамен | Все DONE | Ошибок среди DONE | UNSURE | Правильных итоговых программ |',
        '|---|---:|---:|---:|---:|']
    for name, s in stats.items():
        m = s['main']; fraction = f'{m["wrong_fraction_of_DONE"]:.2%}' if m['all_DONE'] else '—'
        lines.append(f'| {name} | {m["all_DONE"]} | {fraction} | {m["abstained"]} | {m["final_program_correct"]} |')
    lines += ['', '| Классификатор на первом состоянии нового экзамена | Основные /320 | Операции /192 | Завершение /96 |',
        '|---|---:|---:|---:|']
    for name in ['source', 'late-research', 'all-research']:
        lines.append('| '+name+' | '+' | '.join(str(semantic[name][p]['correct']) for p in ['main', 'skills', 'completion'])+' |')
    b, n = semantic['source']['skills'], semantic['all-research']['skills']
    lines += ['', f'На панели операций рост общей точности классификатора оплачен дополнительными '
        f'ложноположительными: {b["false_positive"]} → {n["false_positive"]}. Пропусков верного кода '
        f'стало {b["false_negative"]} → {n["false_negative"]}. Поэтому одной общей точности недостаточно: '
        'следующий опыт должен отдельно ограничивать ошибочное признание неверного кода правильным.', '',
        'Здесь правильность предсказана знаком существующего margin при фиксированном пороге 0; '
        'это диагностическая метрика, она не блокирует DONE и не используется для выбора весов.', '',
        'Успех означает правильную программу, все обязательные публичные исполнения '
        'и DONE. UNSURE при правильном коде успехом не считается.', '',
        'На каждой контрольной панели требуется не меньше успехов и завершённых верных '
        'стартов, не больше ложных DONE, чем у исходной сети. Среди подходящих вариантов '
        'сравнивается (успех − 4×ложные DONE)/размер с весами 0.60/0.25/0.15. Исходная '
        'сеть включена как шаг 0. Профили research выбраны только по контрольной полезности '
        'среди обученных, могут нарушать удержание и не подменяют основной отбор.', '',
        'Контроль и экзамен зафиксированы до SGD. Новые тексты не пересекаются с '
        'предыдущими корпусами. Здесь проверяются новые формулировки и экземпляры '
        'известных семейств; совершенно новые алгоритмические семейства отдельно '
        'не удерживались. Гарантии обобщения на любые программы этот экзамен не даёт.', '',
        '| Семейство операций, новый экзамен | source: решено / всего | Ложных DONE | late-research: решено | Ложных DONE | all-research: решено | Ложных DONE |',
        '|---|---:|---:|---:|---:|---:|---:|']
    tasks = {t['id']: t for t in read(root/'fresh-skills.jsonl')}
    for family in sorted({t['skill_family'] for t in tasks.values()}):
        values = []
        for name in ['source', 'late-research', 'all-research']:
            rows = [r for r in reports[name]['skills']['details'] if tasks[r['id']]['skill_family'] == family]
            values += [str(sum(r['pass'] for r in rows)) + (f'/{len(rows)}' if name == 'source' else ''),
                str(sum(r['finished'] and not r['program_correct'] for r in rows))]
        lines.append('| '+family+' | '+' | '.join(values)+' |')
    lines += ['',
        '| Контроль | Шаг | Основной успех /160 | Ложных DONE | Операции /96 | Ложных DONE | Завершение /48 | Ложных DONE | Удержание |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    dev = load(root, 'initial-development.json')
    for arm in ['source', *ARMS]:
        for step in ([0] if arm == 'source' else policy['checkpoints']):
            r = dev if arm == 'source' else load(root, f'{arm}/development-{step}.json')
            retained = all(p['passed'] >= dev[n]['passed'] and p['false_DONE'] <= dev[n]['false_DONE'] and p['correct_controls_completed'] >= dev[n]['correct_controls_completed'] for n, p in r.items())
            m, k, c = [r[n] for n in ['main', 'skills', 'completion']]
            lines.append(f'| {arm} | {step} | {m["passed"]} | {m["false_DONE"]} | {k["passed"]} | {k["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} | {retained} |')
    lines += ['', 'После обучения, до просмотра новых экзаменационных результатов, отдельно '
        'проверена связь двух выходных головок. В существующий вектор DONE добавляется '
        'β×(вектор «верно» − вектор «неверно»), затем он снова округляется на реальную сетку Q4. '
        'Ни новых параметров исполнения, ни внешнего запрета DONE нет. β выбирается только '
        'по контролю; исходная сеть остаётся вариантом отката. Новых SGD-обновлений нет.', '',
        '| Связь головок, контроль | β | Основной успех /160 | Ложных DONE | Операции /96 | Ложных DONE | Завершение /48 | Ложных DONE | Удержание |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for arm in ARMS:
        for record in load(root, arm+'/coupling-development.json'):
            m, k, c = [record['summary'][n] for n in ['main', 'skills', 'completion']]
            lines.append(f'| {arm} | {record["beta"]} | {m["passed"]} | {m["false_DONE"]} | {k["passed"]} | {k["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} | {record["key"][0]} |')
    lines += ['', 'Выбор связи головок: '+', '.join(f'{arm}: β={r["beta"]}, откат={r["source_fallback"]}' for arm, r in coupling['choices'].items())+'.']
    recommended = root/'export/recommended'
    shutil.copytree(root/'export'/selected if promoted else PARENT/'export/lr10-terminal', recommended, dirs_exist_ok=True)
    if not promoted: lines += ['', '**Новые веса не приняты.** Экспорт `recommended` сохраняет исходную сеть. Контрольный кандидат остаётся исследовательским.']
    paired = {}
    lines += ['', 'Ошибки и регрессии:','']
    for name in [selected, *[a+'-research' for a in ARMS]]:
        paired[name] = {n: transitions(initial[n], p) for n, p in reports[name].items()}
        changes = paired[name]['main']
        lines.append(f'- {name}, основной экзамен: {changes["gained"]} новых успехов, {changes["lost"]} потерянных; '
            f'{changes["removed_false_DONE"]} прежних ложных DONE убраны и {changes["new_false_DONE"]} появились заново.')
        wrong = []; lost = []
        for panel, p in reports[name].items():
            for b, r in zip(initial[panel]['details'], p['details']):
                if r['finished'] and not r['program_correct']: wrong.append({'panel': panel, 'baseline': b, 'episode': r})
                if b['pass'] and not r['pass']: lost.append({'panel': panel, 'baseline': b, 'episode': r})
        for suffix, rows in [('false-DONE', wrong), ('lost-success', lost)]:
            p = root/f'{name}-{suffix}.jsonl'; p.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
            lines.append(f'- {name}: {suffix}, {len(rows)} — [{p.name}]({p}).')
    lines += ['', 'Проверка экспорта и исполнения:','']
    for name, p in native['models'].items():
        if name == 'compiler': continue
        lines.append(f'- {name}: CPU/B200 {p["cpu_matches"]}/{p["probes"]}, C++/B200 {p["native_matches"]}/{p["probes"]}; '
            f'точная повторная упаковка/загрузка Q4; MKA {p["package_bytes"]:,} байт. Все входные строки и неадаптируемые тензоры побитово сохранены.')
    p = native['models'][selected]
    lines += [f'- KV {p["cache_bytes"]:,} байт при 1024 токенах; workspace {p["workspace_bytes"]:,} байт. '
        'Отдельные адаптеры при исполнении не хранятся.',
        '- Данные, учебные исходники и исходные веса проверены по хешам; градиенты во внутренних '
        'адаптерах проверены до SGD, учитель заморожен. Собственные задания завершены, обе B200 свободны.',
        '- Физический PicoCalc не измерялся; прошивка не менялась.']
    lines += ['', 'Следующий опыт должен отделить понимание условия от проверки программы. '
        'Предлагаемый порядок (в этом прогоне ещё не реализован):', '',
        '1. Отдельный тест «условие → требуемая операция/аргумент/режим/ограничения» и '
        '«код + факты → какой эффект получен». Считать ошибки двух этапов отдельно, '
        'проверять новые русские формулировки и сочетания операций.',
        '2. Обучить короткий явный план цели в том же HEX: сначала получить программу-гипотезу '
        'из условия, затем сравнивать её смысл с текущим кодом и запусками. Во время работы '
        'план предсказывает сама сеть; доверенный эталон в runtime не подставляется. '
        'Учитель готовит разнообразные формулировки и объяснения, ROM проверяет метки. '
        'Отдельно измерять качество предсказания плана и полных исправлений.',
        '3. Сравнить такой учебный протокол с текущим при одинаковом бюджете обновлений '
        'и прежних ограничениях выпуска. Сначала проверить один короткий пилот. '
        'Увеличивать объём обучения после подтверждения переноса; текущий опыт не '
        'доказывает ни предел 3M, ни достаточность дальнейшего повторения тех же примеров.']
    path = HERE/'SEMANTIC_CROSS_RESULTS.md'; path.write_text('\n'.join(lines)+'\n')
    summary = {'completed': True, 'new_checkpoint_promoted': promoted, 'selected_arm': selected,
        'selected_step': choice['step'], 'optimizer_updates': 2*policy['steps'], 'new_exam': stats,
        'heldout_nonregression': heldout_retained, 'heldout_false_DONE_improved': false_improved,
        'recommended_profile': selected if promoted else 'source',
        'paired_transitions': paired, 'native_verified': True, 'fresh_used_for_selection': False,
        'initial_semantic_diagnostics': semantic,
        'trainable_parameters': prepared['trainable_parameters'], 'crossed_groups': data['crossed_groups'],
        'physical_device_measured': False}
    summary['coupling'] = coupling
    write(root/'summary.json', summary)
    state = load(HERE, 'work-state.json')
    if not state.get('semantic_cross_v1', {}).get('optimizer_updates_accounted') and not state.get('semantic_cross_v1', {}).get('completed'):
        state['completed_training_runs'] += 2; state['total_accounted_optimizer_updates_lower_bound'] += summary['optimizer_updates']
    state.update(phase='semantic_cross_v1_complete', active_experiment=None, all_own_jobs_complete=True,
        latest_report=str(path), next_action='Next proposed pilot: isolate goal interpretation vs code/effect verification; teach an explicit short HEX goal hypothesis predicted by the student at runtime. No firmware deployment requested.')
    state['semantic_cross_v1'] = {'completed': True, 'optimizer_updates_accounted': True, 'root': str(root), 'report': str(path), 'summary': summary}
    write(HERE/'work-state.json', state)
    print(json.dumps({'completed': True, 'report': str(path), 'selected': selected, 'step': choice['step'], 'promoted': promoted}), flush=True)


if __name__ == '__main__': main()
