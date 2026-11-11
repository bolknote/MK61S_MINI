"""Record the false-DONE experiment, including rejected corrections."""
import argparse
import json
from pathlib import Path
from ak_common import HERE, PARENT, ARMS, read, write


def load(root, name):
    return json.loads((root / name).read_text())


def brief(report):
    out = {}
    for name, p in report.items():
        done = sum(r['finished'] for r in p['details'])
        out[name] = {k: p[k] for k in ['total', 'passed', 'false_DONE', 'premature_DONE',
            'correct_controls_completed', 'abstained', 'unfinished_correct']}
        out[name].update(all_DONE=done,
            wrong_fraction_of_DONE=p['false_DONE'] / done if done else None,
            final_program_correct=sum(r['program_correct'] for r in p['details']))
    return out


def transitions(old, new):
    assert len(old['details']) == len(new['details'])
    pairs = list(zip(old['details'], new['details']))
    assert all(a['id'] == b['id'] for a, b in pairs)
    bad = lambda r: r['finished'] and not r['program_correct']
    return {'gained': sum(not a['pass'] and b['pass'] for a, b in pairs),
        'lost': sum(a['pass'] and not b['pass'] for a, b in pairs),
        'new_false_DONE': sum(not bad(a) and bad(b) for a, b in pairs),
        'removed_false_DONE': sum(bad(a) and not bad(b) for a, b in pairs),
        'new_false_DONE_from_old_success': sum(a['pass'] and bad(b) for a, b in pairs)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', type=Path, required=True)
    root = ap.parse_args().root.resolve()
    native = load(root, 'native-verification.json')
    assert native['complete'] and native['body_generator_protected_in_all_profiles']
    post = load(root, 'postflight.json')
    assert post['all_frozen_data_sources_and_features_verified'] and not post['own_running_containers']
    pre = load(root, 'calibration-preselected.json'); prepared = load(root, 'prepared.json')
    assert pre['fresh_used_for_selection'] is False
    policy = load(root, 'policy.json'); data = load(root, 'data-frozen.json')
    initial = load(root, 'initial-fresh.json'); dev = load(root, 'initial-development.json')
    reports = {'source': initial}
    for arm in ARMS:
        for suffix in ['best', 'research', 'calibrated']:
            reports[arm + '-' + suffix] = load(root, arm + '/' + suffix + '-fresh.json')
    stats = {k: brief(v) for k, v in reports.items()}
    previous = load(PARENT, 'initial-fresh-audit.json')
    old_latest = load(PARENT, 'lr10/terminal-fresh-audit.json')
    prior_panels = ['main', 'skills', 'goals', 'completion']
    prior = {'source': brief({k: previous[k]['raw'] for k in prior_panels}),
        'lr10_terminal': brief({k: old_latest[k]['raw'] for k in prior_panels}),
        'main_transitions': transitions(previous['main']['raw'], old_latest['main']['raw'])}
    choice = pre['choices'][pre['selected_arm']]
    assert all(r['alpha'] == 0 for r in pre['choices'].values()), 'Revise report for an accepted calibration'
    promoted = choice['alpha'] > 0
    old, new = prior['source']['main'], prior['lr10_terminal']['main']
    lines = ['# 3M Q4: причины ложных DONE и проверка коррекции', '',
        '**Ни один новый профиль не принят:** обучение уменьшает число ложных DONE, '
        'но теряет правильные завершения. Слабая смесь тоже не дала улучшения при прежних '
        'строгих условиях отбора. `selected-correction` сохраняет исходные веса AJ lr10-terminal.', '',
        'Причина роста в предыдущем прогоне:', '',
        '| Основной экзамен предыдущего прогона /480 | Исходный distill | AJ lr10-terminal |',
        '|---|---:|---:|']
    for label, key in [('Правильно завершено', 'passed'), ('Все DONE', 'all_DONE'),
                       ('Ложные DONE', 'false_DONE'), ('Правильных итоговых программ', 'final_program_correct')]:
        lines.append(f'| {label} | {old[key]} | {new[key]} |')
    lines += [f'| Ошибок среди DONE | {old["wrong_fraction_of_DONE"]:.2%} | {new["wrong_fraction_of_DONE"]:.2%} |', '',
        'Сеть чаще завершает программу, поэтому растёт и абсолютное число ошибочных завершений. '
        'Условная доля ошибок практически прежняя. Это не объясняет все изменения: '
        f'{prior["main_transitions"]["new_false_DONE"]} ложных DONE появились заново, '
        f'{prior["main_transitions"]["removed_false_DONE"]} прежних исчезли; '
        f'{prior["main_transitions"]["new_false_DONE_from_old_success"]} новых ошибок раньше были успехами.', '',
        'На панели операций/аргументов правильных итоговых программ было '
        f'{prior["source"]["skills"]["final_program_correct"]}, стало '
        f'{prior["lr10_terminal"]["skills"]["final_program_correct"]}. '
        'Совместное обучение затрагивало и генерацию кода. Предыдущая выборка и дополнительная '
        'потеря поощряли завершение правильного кода; отдельная оценка корректности не управляла '
        'raw-выбором DONE. Это объяснение согласуется с измерениями, но отдельной абляцией причин не проверено.', '',
        'Проверенная коррекция:', '',
        f'- Заморожены все слои генератора, входной русский словарь и строки HEX. Обучались '
        'только вектор DONE (128 параметров) или пять векторов действий (640 параметров).',
        f'- Подготовлено {data["training_states"]} состояний; {prepared["feature_rows"]} помещаются в контекст. '
        f'В том числе {prepared["groups"]["proposal"]} настоящих ложных DONE и '
        f'{prepared["groups"]["danger"]} неправильных программ после завершённых публичных RUN.',
        '- В батче 256 строк: 64 фактических ложных DONE, 64 других опасных состояния, '
        '64 правильных завершения, 32 незавершённых проверки и 32 остальных шага. '
        'Штраф вероятности DONE на неподходящих состояниях имеет вес 4; сохраняются '
        'распределения действий, которые исходная сеть выбирала правильно.',
        f'- По {policy["steps"]} обновлений на двух B200, всего {len(ARMS)*policy["steps"]}. '
        'Обучение и все экзамены используют реальную сетку Q4. Новых слоёв и параметров при исполнении нет.',
        '- Решения raw: внешнего запрета DONE, эталонного ответа и скрытых тестов на входе нет.', '',
        'До SGD зафиксированы новый контроль (160 основных, 96 операций, 48 завершений) и '
        'экзамен (320 основных, 192 операций, 96 завершений). Точные тексты не пересекаются '
        'с обучением; это новые формулировки и экземпляры знакомых семейств, а не доказательство '
        'обобщения на любые программы МК-61. Прежние экзамены используются для обучения.', '',
        '| Новый экзамен Q4 | Успех /320 | Ложных DONE | Операции /192 | Ложных DONE | Завершение /96 | Ложных DONE |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name in ['source', 'done-research', 'actions-research', pre['selected_arm'] + '-calibrated']:
        m, s, c = [stats[name][n] for n in ['main', 'skills', 'completion']]
        lines.append(f'| {name} | {m["passed"]} | {m["false_DONE"]} | {s["passed"]} | {s["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} |')
    lines += ['', 'Успех требует правильной программы, всех обязательных публичных исполнений и DONE. '
        'Правильный код без завершения успехом не считается. Один и тот же эпизод считается один раз.', '',
        '| Новый экзамен Q4 | Все DONE | Ошибок среди DONE | UNSURE | Итоговый код правилен |',
        '|---|---:|---:|---:|---:|']
    for name in ['source', 'done-research', 'actions-research']:
        p = stats[name]['main']; lines.append(f'| {name} | {p["all_DONE"]} | {p["wrong_fraction_of_DONE"]:.2%} | {p["abstained"]} | {p["final_program_correct"]} |')
    lines += ['', 'Генератор побитово одинаков при одинаковом запросе. Итоговые программы '
        'в эпизодах могут различаться: новое действие меняет последующую историю. '
        'Снижение ложных DONE здесь частично оплачено отказами и незавершёнными верными программами.', '',
        'На каждой контрольной панели требуются: не меньше успехов, не меньше завершённых '
        'верных стартов и не больше ложных DONE, чем у исходной сети. Затем сравнивается '
        '(успех − 4×ложные DONE)/размер с весами 0.60/0.25/0.15. Исходные веса включены в отбор. '
        'Профили research выбраны только по контрольной полезности и явно не прошли удержание.', '',
        'После основного обучения, до просмотра новых экзаменационных результатов, проверена '
        'смесь исходных и обученных строк. Статический контроль отобрал две силы коррекции '
        'для каждой ветки; затем выполнены полные эпизоды с прежним строгим отбором. '
        'Новых обновлений оптимизатора при калибровке не было.', '',
        '| Контроль | Сила смеси | Основной успех | Ложных DONE | Операции | Ложных DONE | Завершение | Ложных DONE | Все условия |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    controls = [('source', 0, dev, True)]
    for arm in ARMS:
        for r in load(root, arm + '/calibration-development.json'):
            controls.append((arm, r['alpha'], r['summary'], r['key'][0]))
    for name, alpha, r, retained in controls:
        m, s, c = [r[n] for n in ['main', 'skills', 'completion']]
        lines.append(f'| {name} | {alpha} | {m["passed"]} | {m["false_DONE"]} | {s["passed"]} | {s["false_DONE"]} | {c["passed"]} | {c["false_DONE"]} | {retained} |')
    lines += ['', 'В обеих ветках выбрана сила 0: безопасные слабые изменения не улучшили метрики, '
        'а более сильные нарушили удержание. Экзамен не использовался для выбора силы или весов.', '',
        'Проверка исполнения:', '']
    for name, r in native['models'].items():
        if name == 'compiler': continue
        lines.append(f'- {name}: точная повторная упаковка Q4; CPU/B200 {r["cpu_matches"]}/{r["probes"]}, '
            f'C++/B200 {r["native_matches"]}/{r["probes"]}; все защищённые тензоры и входные строки побитово прежние.')
    p = native['models'][pre['selected_arm'] + '-calibrated']
    lines += [f'- Модель 3 022 080 параметров, MKA {p["package_bytes"]:,} байт, '
        f'контекст 1024, KV {p["cache_bytes"]:,} байт; новых затрат памяти для головок нет.',
        f'- Проверены {native["long_prefixes_checked"]} длинных префиксов; корпус, исходники, '
        'исходные веса и признаки сверены по хешам. Собственные контейнеры завершены, обе B200 свободны.',
        '- Физический PicoCalc не измерялся; прошивка не менялась.', '',
        'Следующее изменение обучения должно улучшать само распознавание ошибки, а не только '
        'снижать частоту DONE. Для этого нужны пары почти одинаковых программ с разным результатом '
        '(X²/X⁴, аргумент, порядок операций), явное сопоставление условия с трассой и проверенные '
        'продолжения «нашёл расхождение → исправил → повторил RUN → DONE». Этот опыт показывает, '
        'что одной линейной поправки пяти действий поверх замороженных признаков недостаточно '
        'для выполненных условий качества; это не доказательство невозможности другого обучения.', '',
        'Оставшиеся ошибки и регрессии сохранены отдельно:', '']
    paired = {}
    for name in ['done-research', 'actions-research', pre['selected_arm'] + '-calibrated']:
        r = reports[name]; paired[name] = {n: transitions(initial[n], p) for n, p in r.items()}
        wrong = []; lost = []
        for panel, p in r.items():
            for b, n in zip(initial[panel]['details'], p['details']):
                if n['finished'] and not n['program_correct']:
                    wrong.append({'panel': panel, 'episode': n, 'baseline': b})
                if b['pass'] and not n['pass']:
                    lost.append({'panel': panel, 'episode': n, 'baseline': b})
        for suffix, rows in [('false-DONE', wrong), ('lost-success', lost)]:
            file = root / f'{name}-{suffix}.jsonl'
            file.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
            lines.append(f'- {name}: {suffix}, {len(rows)} эпизодов — [{file.name}]({file}).')
    path = HERE / 'DONE_RISK_RESULTS.md'; path.write_text('\n'.join(lines) + '\n')
    summary = {'completed': True, 'new_checkpoint_promoted': promoted, 'selected_arm': pre['selected_arm'],
        'selected_alpha': choice['alpha'], 'optimizer_updates': len(ARMS) * policy['steps'],
        'prior_diagnosis': prior, 'new_exam': stats, 'paired_transitions': paired,
        'generator_bit_identical': True, 'native_verified': True,
        'fresh_used_for_selection': False, 'physical_device_measured': False}
    write(root / 'summary.json', summary)
    state_path = HERE / 'work-state.json'; state = load(HERE, 'work-state.json')
    if not state.get('done_risk_v1', {}).get('completed'):
        state['completed_training_runs'] += len(ARMS)
        state['total_accounted_optimizer_updates_lower_bound'] += summary['optimizer_updates']
    state.update(phase='done_risk_v1_complete', active_experiment=None, all_own_jobs_complete=True,
        latest_report=str(path), next_action='Review frozen-generator correction: no new checkpoint promoted; improve semantic error recognition.')
    state['done_risk_v1'] = {'completed': True, 'root': str(root), 'report': str(path), 'summary': summary}
    write(state_path, state)
    print(json.dumps({'completed': True, 'report': str(path), 'new_checkpoint_promoted': promoted}), flush=True)


if __name__ == '__main__':
    main()
