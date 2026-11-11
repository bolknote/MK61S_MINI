"""Report the standalone critic, including rejection rates and transfer limits."""
import argparse
import json
from pathlib import Path
from ao_common import HERE, ARMS, CLASSES, read, write
from ao_eval import brief, key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    root = ap.parse_args().root.resolve()
    frozen = json.loads((root / 'data-frozen.json').read_text())
    native = json.loads((root / 'native-verification.json').read_text())
    post = json.loads((root / 'postflight.json').read_text())
    assert native['complete'] and not post['own_running_containers']
    pre = json.loads((root / 'preselected.json').read_text())
    assert not pre['fresh_used_for_selection']
    selected = pre['selected_arm']
    scores = {a: {s: json.loads((root / a / (s + '.json')).read_text()) for s in ['fresh', 'novel-fresh']} for a in ARMS}
    training = {a: json.loads((root / a / 'training.json').read_text()) for a in ARMS}
    assert training['head']['same_draw_digest'] == training['adapt']['same_draw_digest']
    updates = sum(t['steps'] for t in training.values())
    eligible = {a: {s: bool(key(v)[0]) for s, v in panels.items()} for a, panels in scores.items()}
    accepted = all(eligible[selected].values())
    policy = json.loads((root / 'policy.json').read_text())
    lines = ['# Отдельное распознавание ошибок МК-61: Q4', '',
      ('Выбранный по контролю критик прошёл пороги распознавания на обеих новых панелях.' if accepted else
       '**Критик пока недостаточно надёжен для практического завершения задач.** Выбранные веса не прошли пороги качества.'), '',
      'Проведены два независимых варианта одного опыта: `head` обучает только 512 коэффициентов четырёх выходных строк; '
      '`adapt` дополнительно обучает 317 440 коэффициентов адаптеров внимания и MLP. '
      'Оба получают одни и те же учебные группы, с одинаковым порядком и балансом классов. '
      'Начальные веса — экспорт AN direct-research; основной генератор и его режим исполнения не заменялись.', '',
      f'Обучение: {frozen["row_counts"]["train"]} примеров, по одному из четырёх классов для каждого из '
      f'{frozen["group_counts"]["train"]} условий. По {policy["steps"]} шагов на двух B200, всего {updates} обновлений. '
      'Все прямые проходы обучения и все экзамены используют реальную сетку Q4; математика обучения FP32.', '',
      'Классы: замена операции, ошибка аргумента, ошибка порядка команд, правильная программа. '
      'Ошибочный порядок сохраняет весь набор байтов команд и меняет их последовательность. '
      'Это отдельная проверка, а не подмена X² на X⁴. Все четыре кандидата успешно останавливаются; '
      'каждый неверный имеет контрпример среди трёх публичных исполнений ROM. '
      'Сверяются X и R0–RE. Остановка сама по себе не означает правильность.', '',
      'Вход — русское условие, HEX, константы, публичные входы и фактические результаты эмулятора. '
      'Эталон, ожидаемые значения и скрытые тесты во вход не подаются. '
      'Выход — один из четырёх классов; этот опыт не обучает свободные рассуждения или исправление программы.', '',
      f'Ветка `{selected}` и её шаг выбраны только по основной контрольной панели до открытия экзамена. '
      'Новые комбинации операций контролируются отдельно; их пары не встречались в обучении. '
      'На основном экзамене новые русские формулировки, регистры и константы знакомых семейств. '
      'Обе панели имеют точный баланс четырёх классов; постоянный ответ даёт 25% точности.', '',
      '| Q4, новые задачи | Верный класс | Macro-F1 | Ошибочный код принят правильным | Правильный код отвергнут |',
      '|---|---:|---:|---:|---:|']
    for arm, panels in scores.items():
        for split, m in panels.items():
            lines.append(f'| {arm}, {split} | {m["correct"]}/{m["total"]} ({m["accuracy"]:.1%}) | '
                         f'{m["macro_F1"]:.3f} | {m["false_correct"]}/{m["incorrect_total"]} ({m["false_correct_rate"]:.1%}) | '
                         f'{m["false_error"]}/{m["correct_total"]} ({m["false_error_rate"]:.1%}) |')
    lines += ['', 'Доля ошибочного кода, названного правильным, — отдельная метрика классификатора. '
              'Она не является долей ложных DONE в агентных эпизодах: критик пока не подключён к действию DONE.', '',
              '| Полнота класса | operation | argument | order | correct |', '|---|---:|---:|---:|---:|']
    for arm, panels in scores.items():
        for split, m in panels.items():
            lines.append('| ' + arm + ', ' + split + ' | ' + ' | '.join(f'{m["recall"][c]:.1%}' for c in CLASSES) + ' |')
    for arm, panels in scores.items():
        for split, m in panels.items():
            lines += ['', f'Матрица `{arm}/{split}`: строки — правильные классы, столбцы — предсказания.', '',
                      '| Истинный класс | operation | argument | order | correct |', '|---|---:|---:|---:|---:|']
            lines += ['| ' + c + ' | ' + ' | '.join(map(str, row)) + ' |'
                      for c, row in zip(CLASSES, m['confusion_expected_rows_predicted_columns'])]
    lines += ['', '| Контроль Q4 | Шаг | Macro-F1 | Минимальная полнота | Ложное «правильно» |', '|---|---:|---:|---:|---:|']
    for arm in ARMS:
        for step in policy['checkpoints']:
            for split in ['development', 'novel-development']:
                m = json.loads((root / arm / f'{split}-{step}.json').read_text())
                lines.append(f'| {arm}, {split} | {step} | {m["macro_F1"]:.3f} | {m["minimum_recall"]:.1%} | {m["false_correct_rate"]:.1%} |')
    lines += ['', 'Зафиксированные пороги: macro-F1 ≥ 0,85, полнота каждого класса ≥ 80%, '
              'не более 5% неверных программ признаны правильными. Экзамен не меняет выбранный чекпойнт. '
              'Публикация исследовательского экспорта не означает принятие модели в harness.', '',
              'Границы результата: короткие арифметические программы и операции с регистрами; '
              'одна внесённая ошибка в кандидате. Циклы, ветвления, длинные игровые программы, '
              'несколько одновременных ошибок и весь стандартный набор команд этим экзаменом не покрываются.', '',
              '| Семейство | Ветка | Верных классов на fresh |', '|---|---|---:|']
    for arm in ARMS:
        for family, m in scores[arm]['fresh']['by_family'].items():
            lines.append(f'| {family} | {arm} | {m["correct"]}/{m["total"]} ({m["accuracy"]:.1%}) |')
    error_counts = {}
    for arm in ARMS:
        errors = []; false_correct = []
        for split in ['fresh', 'novel-fresh']:
            mapping = {r['id']: (r, g['task']) for g in read(root / (split + '.jsonl')) for r in g['rows']}
            for r in scores[arm][split]['details']:
                if r['label'] == r['predicted']:
                    continue
                row, task = mapping[r['id']]
                item = {'split': split, 'expected': CLASSES[r['label']], 'predicted': CLASSES[r['predicted']],
                        'row': row, 'task_offline_only': task, 'logits': r['logits']}
                errors.append(item)
                if r['label'] != 3 and r['predicted'] == 3:
                    false_correct.append(item)
        for suffix, values in [('errors', errors), ('false-correct', false_correct)]:
            path = root / f'{arm}-{suffix}.jsonl'
            path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in values))
            lines += ['', f'[{arm}: {suffix}, {len(values)} примеров]({path}).']
        error_counts[arm] = {'errors': len(errors), 'false_correct': len(false_correct)}
    lines += ['', 'Дальше требуется учить семантическую проверку, а не только название дефекта: '
              'сначала восстановление операции и аргументов из условия и HEX отдельно, затем сравнение с фактическим '
              'исполнением. Перенос на удержанные сочетания должен улучшаться до подключения критика к DONE. '
              'Текущий результат не оправдывает увеличение числа одинаковых шагов без нового учебного сигнала.', '',
              'Нативная проверка и экспорт:', '']
    for arm, m in native['models'].items():
        lines.append(f'- `{arm}`: CPU/B200 и C++/B200 совпали по классу на {m["probes"]}/{m["probes"]} заранее выбранных пробах; '
                     f'максимальная разница логитов {max(v["native_logit_error"] for v in m["details"]):.6f}. '
                     f'MKA {m["package_bytes"]:,} байт, KV {m["cache_bytes"]:,} байт, окно 1024 токена.')
    lines += ['- 3 022 080 исполняемых параметров. Входной русский словарь и неадаптируемые тензоры побитово сохранены.',
              '- SHA учебных данных, исходных весов и замороженных исходников проверены. Все собственные GPU-задания завершены.',
              '- Физический PicoCalc не измерялся; прошивка не менялась.', '',
              f'[Q4-критик adapt]({root/"export/adapt/model.mka"}); '
              f'[полная проверка C++]({root/"native-verification.json"}); '
              f'[исходник runner]({HERE/"ao_native.py"}).']
    overhead_path = root.parent / 'prompt-overhead.json'
    overhead = json.loads(overhead_path.read_text()) if overhead_path.exists() else None
    if overhead:
        saved = overhead['saved_min_median_max'][1]
        lines += ['', 'Отдельный расчёт постоянных инструкций', '',
                  f'На 4800 учебных входах удаление повторяемых инструкций при сохранении динамического режима '
                  f'освобождает {saved:g} токенов: медиана {overhead["original_min_median_max"][1]:g} → '
                  f'{overhead["short_min_median_max"][1]:g}. '
                  f'FP32 KV занимает {overhead["kv_bytes_per_token"]} байт на позицию; '
                  f'при уменьшении выделяемого окна это {int(saved*overhead["kv_bytes_per_token"]):,} байт. '
                  'При прежнем окне 1024 память не меняется, но появляется больше места для полезного состояния.', '',
                  'Для удаления инструкций нужен отдельный опыт с дистилляцией контекста и проверкой Q4. '
                  'Предварительное вычисление KV не освобождает хранилище KV. '
                  'В этом обучении формат не сокращался. '
                  '[Первичное описание context distillation](https://arxiv.org/html/2112.00861v3#S2.SS1).']
    path = HERE / 'ERROR_RECOGNIZER_RESULTS.md'
    path.write_text('\n'.join(lines) + '\n')
    summary = {'completed': True, 'selected_arm': selected, 'standalone_critic_accepted': accepted,
               'main_actor_changed': False, 'optimizer_updates': updates,
               'fresh_used_for_selection': False, 'native_verified': True,
               'metrics': {a: {s: brief(v) for s, v in panels.items()} for a, panels in scores.items()},
               'release_eligibility': eligible, 'error_counts': error_counts, 'prompt_overhead': overhead,
               'physical_device_measured': False}
    write(root / 'summary.json', summary)
    state = json.loads((HERE / 'work-state.json').read_text())
    if not state.get('error_recognizer_v1', {}).get('completed'):
        state['completed_training_runs'] += 2
        state['total_accounted_optimizer_updates_lower_bound'] += updates
    state.update(phase='error_recognizer_v1_complete', active_experiment=None, all_own_jobs_complete=True,
                 latest_report=str(path), next_action='Review semantic recognition failures and context distillation; no firmware deployment requested.')
    state['error_recognizer_v1'] = {'completed': True, 'root': str(root), 'report': str(path), 'summary': summary}
    write(HERE / 'work-state.json', state)
    print(json.dumps({'completed': True, 'report': str(path), 'selected': selected, 'critic_accepted': accepted}), flush=True)


if __name__ == '__main__':
    main()
