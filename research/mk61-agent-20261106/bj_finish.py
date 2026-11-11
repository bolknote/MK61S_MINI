"""Publish the completed experiment and account only actual optimizer updates."""
import json
import time
from bj_common import ROOT, HERE, read, write, sha, check_frozen


def main():
    check_frozen(); result = ROOT / 'server-results'
    assert read(result / 'complete.json')['complete']
    assert read(result / 'native-verification.json')['complete']
    steps = {a: read(result / a / 'training.json')['optimizer_updates'] for a in ['lora', 'full']}
    assert steps == {'lora': 6000, 'full': 6000}
    assert read(result / 'lora/training.json')['draw_digest'] == read(result / 'full/training.json')['draw_digest']
    reports = {a: read(result / a / 'closed.json') for a in ['parent_lora', 'parent_full', 'lora', 'full', 'fixed6000_lora', 'fixed6000_full']}
    selection = read(result / 'preselected.json'); teacher = read(ROOT / 'teacher-frozen.json')
    lines = ['# SPEC intent and recovery: LoRA / full 3M', '',
        'Все этапы завершены. Проверка в Q4, контекст 1024, вычисления и KV FP32. '
        'Основной профиль и прошивка не заменялись. Новый runtime проверен на компьютере; на PicoCalc не перенесён.', '',
        '## Диагностика с эталонной SPEC', '',
        'Эталон был доступен только проверяющему модулю. У модели оставались обычное русское условие и прежняя политика действий. '
        'Нулевые ложные DONE здесь характеризуют проверяющий модуль, а не приобретённый навык модели.', '',
        '| Ветка | Успешные завершения /512 | Исправления /256 | Порча /256 | Правильный итоговый код /512 |',
        '|---|---:|---:|---:|---:|']
    for arm in ['lora', 'full']:
        r = read(ROOT / 'oracle' / arm / 'results.json'); a = r['baseline']; b = r['gold_checker']
        lines.append(f"| {arm} | {a['passed']} → {b['passed']} | {a['wrong_starts_repaired']} → {b['wrong_starts_repaired']} | {a['correct_starts_corrupted']} → {b['correct_starts_corrupted']} | {a['final_correct_code']} → {b['final_correct_code']} |")
    lines += ['', '## Изменения упряжи и обучения', '',
        '- PUBLIC_RUNS запускает только недостающие публичные случаи. SPEC_DOMAIN допускает один повторный разбор русского условия без текущего кода.',
        '- DIAG 04 FF FF 00 00 сообщает об ошибке гипотезы и вызывает тот же разбор. Новая SPEC считается гипотезой; её согласованность с кодом не доказывает понимания запроса.',
        '- WRITE создаёт пробную версию. Если эпизод не завершён принятым DONE, код откатывается к состоянию перед первым WRITE. Принятый ошибочный DONE этим не маскируется.',
        '- Считаются отдельно ложные заявления DONE и ложные принятые DONE. Повторный разбор и автоматические RUN расходуют прежний бюджет 12 действий.',
        '- Учитель DeepSeek-V4.1-Flash готовил и проверял русские формулировки. Четыре сочетания верной/неверной SPEC и верного/неверного кода размечены по AST и настоящему эмулятору, без доверия к мнению учителя о корректности HEX.',
        '- В каждом батче 8 примеров перевода условия, 4 повторного разбора, 12 строк из сбалансированных четвёрок и 8 строк повтора старых исправлений и инструментальных циклов.',
        '- Продолжены собственные BH fixed6000-родители. По 6000 обновлений на ветку, одинаковые выборки. LoRA:318208 обучаемых параметров; полная:3022080.',
        '- Старые открытые экзамены выведены из тестирования и могут входить в учебный банк. Новый экзамен не пересекается с ними и обучением по нормализованным целевым выражениям; новые числа и сочетания операций отделены до обучения.',
        '- Проверка формулировок проводилась тем же учителем, в двух слепых подачах для новых естественных тестовых условий; это не независимая человеческая валидация.', '',
        'Новый корпус:', '', '| Часть | Выражения | Формулировки |', '|---|---:|---:|',
        *[f"| {s} | {c['trees']} | {c['questions']} |" for s, c in teacher['counts'].items()], '',
        '## Новый закрытый экзамен: фактически обученные веса шага 6000', '',
        'Сравнение с собственным родителем в той же новой упряжи. Успешное исправление требует верного кода, выполненных RUN и принятого DONE.', '',
        '| Ветка | Исправления | Порча верного кода | Ложные принятые DONE | Успешные завершения | Эпизоды с ложными заявлениями DONE |',
        '|---|---:|---:|---:|---:|---:|']
    for arm in ['lora', 'full']:
        a = reports['parent_' + arm]['self']['summary']; b = reports['fixed6000_' + arm]['self']['summary']
        keys = ['wrong_starts_repaired', 'correct_starts_corrupted', 'false_DONE', 'passed', 'episodes_with_false_DONE_claims']
        lines.append('| ' + arm + ' | ' + ' | '.join(f'{a[k]} → {b[k]}' for k in keys) + ' |')
    lines += ['', 'Сравнение с прежним циклом того же родителя на этих же новых условиях:', '',
        '| Ветка | Исправления: прежний → новый обученный цикл | Порча | Ложные принятые DONE | Успешные завершения |',
        '|---|---:|---:|---:|---:|']
    for arm in ['lora', 'full']:
        a = reports['parent_' + arm]['legacy_self']['summary']; b = reports['fixed6000_' + arm]['self']['summary']
        lines.append('| ' + arm + ' | ' + ' | '.join(f'{a[k]} → {b[k]}' for k in ['wrong_starts_repaired', 'correct_starts_corrupted', 'false_DONE', 'passed']) + ' |')
    lines += ['', 'Перевод обычных русских условий в программу, без инструментальных циклов:', '', '| Ветка | Родитель | Шаг 6000 |', '|---|---:|---:|']
    for arm in ['lora', 'full']:
        a = reports['parent_' + arm]['primary']['natural']; b = reports['fixed6000_' + arm]['primary']['natural']
        lines.append(f"| {arm} | {a['passed']}/{a['total']} | {b['passed']}/{b['total']} |")
    lines += ['', 'Навык распознавания ошибки гипотезы и код до механического отката:', '',
        '| Ветка | DIAG04 для неверной SPEC: родитель → обученная | Неверные кандидаты при верном старте до отката | Откаты | Правильные кандидаты без завершения |',
        '|---|---:|---:|---:|---:|']
    for arm in ['lora', 'full']:
        a = reports['parent_' + arm]['discrimination']['bad_spec']; b = reports['fixed6000_' + arm]['discrimination']['bad_spec']
        r = reports['fixed6000_' + arm]['self']; records = r['records']; m = r['summary']
        before_rollback = sum(x['initially_correct'] and not x['candidate_correct_at_exit'] for x in records)
        lines.append(f"| {arm} | {a['detected']}/{a['total']} → {b['detected']}/{b['total']} | {before_rollback}/{m['correct_starts']} | {m['rollbacks']} | {m['uncommitted_correct_candidates']} |")
    lines += ['', '## Выбор и ограничения', '',
        'Выбор по development заморожен до открытия нового закрытого экзамена:', '',
        '| Ветка | Выбранный шаг |', '|---|---:|',
        *[f"| {arm} | {selection['branches'][arm]['step']} |" for arm in ['lora', 'full']], '',
        'Если выбрана ступень 0, это возврат к исходному профилю, а не объявление новой упряжи улучшением. '
        'Диагностика фиксированного шага 6000 обязательна независимо от выбора; её результаты приведены выше. '
        'Закрытый экзамен не использовался для подбора весов, порогов или вариантов runtime.', '',
        'Механический откат уменьшает порчу незавершённых попыток; это свойство упряжи. '
        'Навык сети оценивается также по предложенному коду до отката, четырём классам ошибок и ложным заявлениям DONE.', '',
        '## Артефакты и проверка', '',
        '- `.build/mk61-agent-20261106/spec-intent-recovery-v1/frozen.json`: данные, исходники, родители и протокол до обучения.',
        '- `server-results/{parent_lora,parent_full,lora,full,fixed6000_lora,fixed6000_full}/closed.json`: все ответы и траектории.',
        '- `server-results/export/`: HF, упакованные Q4, MKA и протокол. Экспорт MKA проверяет инференс; новая логика упряжи пока реализована на компьютере.',
        '- `server-results/native-verification.json`: точная загрузка Q4 и совпадение потоков токенов B200/CPU/C++.',
        '- `oracle/`: отдельная диагностика с эталонной SPEC, не продуктовая оценка.',
        '- `server-results/postflight.json`: завершение обоих процессов и проверка замороженных файлов.', '']
    report = HERE / 'SPEC_INTENT_RECOVERY_RESULTS.md'; report.write_text('\n'.join(lines))
    statepath = HERE / 'work-state.json'; state = read(statepath)
    entry = state['latest_intent_recovery_training']
    if not entry.get('ledger_accounted'):
        state['completed_training_runs'] += 2
        state['total_accounted_optimizer_updates_lower_bound'] += sum(steps.values())
    state['latest_intent_recovery_training'].update(phase='complete', complete=True, ledger_accounted=True, optimizer_updates=sum(steps.values()),
        report=str(report), selection=selection, fixed6000={a: reports['fixed6000_' + a]['self']['summary'] for a in ['lora', 'full']}, unix=time.time())
    state['active_experiment'] = None; state['all_own_jobs_complete'] = True; write(statepath, state)
    write(ROOT / 'finish.json', {'complete': True, 'optimizer_updates': sum(steps.values()), 'ledger_accounted': True,
                                'report_sha256': sha(report), 'unix': time.time()})
    print(json.dumps({'complete': True, 'report': str(report), 'selection': selection, 'updates': sum(steps.values())}), flush=True)


if __name__ == '__main__':
    main()
