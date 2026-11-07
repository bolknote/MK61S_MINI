"""Package final neural and explicitly hybrid results without conflating them."""
import hashlib
import json
from pathlib import Path
import shutil

from distill_finish import short
from tasks import BUILD,HERE


def read(path):return json.loads(path.read_text())


def main():
    root=BUILD/'distill-hard';source=root/'server-results'
    if read(source/'status.json')['phase']!='hard_round_complete':raise ValueError('Hard experiment is still active')
    if not(source/'repair-complete.json').exists():raise ValueError('Hybrid evaluation is still active')
    selected=read(source/'preselected.json')['arm']
    report={'selected_by_validation':selected,'policy':read(source/'policy.json'),'frozen':read(source/'frozen.json'),
            'data':read(source/'data-manifest.json'),'models':{},'hybrid':{},
            'host_activations_and_kv':'FP32; real Q4 packing/reload','native_picocalc_runtime_implemented':False}
    report['initial_models']={}
    for name in ['original','previous']:
        path=source/'results'/f'{name}-q4-fresh.json'
        if path.exists():report['initial_models'][name]=short(read(path))
    for arm in ['baseline','dpo','text-only']:
        model_source=BUILD/'distill-v1/export/direct/hf'if arm=='baseline'else source/arm/'best'
        export=root/'export'/arm;hf=export/'hf';hf.mkdir(parents=True,exist_ok=True)
        for p in model_source.iterdir():
            if p.is_file():shutil.copy2(p,hf/p.name)
        q4=export/'model.mkq4';shutil.copy2(source/'results'/f'{arm}-q4-fresh.mkq4',q4)
        scores={}
        for fmt in ['q4','fp32']:
            for split in ['fresh','formal','opened-audit']:
                scores[fmt+':'+split]=short(read(source/'results'/f'{arm}-{fmt}-{split}.json'))
        scores['q4:validation']=short(read(source/'results'/f'{arm}-q4-validation.json'))
        manifest={'arm':arm,'parameters':3017984,'context':512,'q4_file':str(q4),'q4_bytes':q4.stat().st_size,
            'q4_sha256':hashlib.sha256(q4.read_bytes()).hexdigest(),'hf_directory':str(hf),
            'hf_sha256':hashlib.sha256((hf/'model.safetensors').read_bytes()).hexdigest(),
            'tokenizer_bytes':(hf/'tokenizer.json').stat().st_size,'scores':scores,
            'hide_public_examples_from_initial_model_prompt':arm=='text-only'}
        if arm!='baseline':manifest['training']=read(source/arm/'training.json')
        (export/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');report['models'][arm]=manifest
    for split in ['fresh','formal','validation']:
        value=read(source/f'repair-{split}.json')
        report['hybrid'][split]={k:v for k,v in value.items()if k!='details'}
    report['hybrid']['policy']=read(source/'repair-policy.json')
    selected_scores=report['models'][selected]['scores'];n=selected_scores['q4:fresh'];f=selected_scores['q4:formal']
    neural_target=n['passed']/n['total']>=.8 and f['passed']/f['total']>=.95
    h=report['hybrid']['fresh'];hf=report['hybrid']['formal']
    hybrid_target=h['hybrid_passed']/h['total']>=.8 and hf['hybrid_passed']/hf['total']>=.95
    report.update(neural_quality_target_met=neural_target,hybrid_example_guided_quality_target_met=hybrid_target)
    (root/'final-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Flourish: обучение с учителем, проверка Q4 и харнесс','',
        '**Оценки нейросети и системы с автоматическим поиском приведены отдельно.** '
        'Гибрид требует числовых примеров с ожидаемыми ответами. Его успешность зависит от модели и алгоритма поиска.','',
        '| Вариант | Новые русские условия, Q4 | Формальные задачи, Q4 |',
        '| --- | ---: | ---: |']
    labels={'baseline':'После учителя, до нового этапа','dpo':'DPO и SFT на программах','text-only':'SFT без исходных числовых примеров'}
    for name,label in [('original','Исходная Flourish'),('previous','До обучения с большим учителем')]:
        if name in report['initial_models']:
            s=report['initial_models'][name];lines.append(f"| {label} | {s['passed']}/{s['total']} | — |")
    for arm in ['baseline','dpo','text-only']:
        s=report['models'][arm]['scores'];a=s['q4:fresh'];b=s['q4:formal']
        lines.append(f"| {labels[arm]} | {a['passed']}/{a['total']} | {b['passed']}/{b['total']} |")
    lines.append(f"| Выбранная модель + ограниченная починка | {h['hybrid_passed']}/{h['total']} | {hf['hybrid_passed']}/{hf['total']} |")
    lines+=['',f'Перед итоговой проверкой по валидации выбран **{selected}**. '
        'Выбор требует не менее 95% на 20 формальных задачах, затем сравнивает точность на 64 русских условиях. '
        'В итоговой новой выборке 32 расчёта имеют по две разные формулировки: это 64 условия, а не 64 новых семейства алгоритмов.','',
        '## Что получилось у модели','',
        'Исходная Flourish-3M содержит 3 017 984 параметра. Доменное обучение использовало 462 исторических листинга '
        'и отобранные фрагменты девяти русских книг. Следующие этапы использовали описания от большой Qwen, '
        'слепой обратный разбор смысла, реальные исполнения эталонов и исправления ошибок ученика. '
        'После фильтров осталось 3 445 разных описаний. Сохранены все промежуточные веса и журналы.','',
        'Этап с учителем дал 30/64 на предыдущей новой русской выборке против 13/64 у прежней модели без плана '
        'и 0/64 у исходной. Формальная регрессия — 96/98. Короткая формула перед кодом оказалась слабее '
        'непосредственного вывода кода в этом эксперименте. [Результаты этапа](DISTILLATION_RESULTS.md).','',
        'Последний этап сравнил Q4-aware DPO с SFT и обучение по тексту без заранее показанных числовых примеров. '
        'Для DPO проверены 4 276 правильных/ошибочных пар; положительные и отрицательные программы исполнялись на микрокодном ядре. '
        'Новая итоговая выборка зафиксирована до градиентов, предыдущая использовалась только как диагностическая. '
        'Метод предпочтений основан на [DPO](https://arxiv.org/abs/2305.18290); сочетание с QAT и SFT — рецепт этого опыта.','',
        f"Рабочий порог для самой модели {'достигнут'if neural_target else'не достигнут'}. "
        f"Порог для гибрида с числовыми примерами {'достигнут'if hybrid_target else'не достигнут'}. "
        'Эти результаты относятся к ограниченной арифметике, регистрам и отдельной проверке ветвлений/циклов. '
        'Генерация полной новой игры и универсальные рассуждения не проверены.','',
        '## Как работает починка','',
        'После трёх неудачных ходов модели харнесс может перебрать до 512 кандидатов. '
        'Он меняет арифметическую команду или регистр, удаляет/вставляет команду, переставляет соседние чтения '
        'и пробует простые программы. Второй шаг поиска использует ограниченный beam. '
        'Поиск получает только публичные числовые входы и ожидаемые ответы; текст условия, эталонная программа '
        'и скрытые входы ему не передаются.','',
        'Первая программа, прошедшая показанные примеры, один раз оценивается на скрытых входах. '
        'Скрытая ошибка не разрешает продолжить поиск. После публичного PASS починка не запускается. '
        'Запросы изменения памяти и неподдерживаемые команды не исправляются этим арифметическим поиском. '
        'Пять интеграционных проверок покрывают бюджет, реальные исполнения и неоднозначность публичных примеров.','',
        f"На новых условиях поиск выполнил {h['emulator_candidate_trials']} проб суммарно; "
        f"предел — {h['candidate_budget_per_failed_task']} на неудачное условие. "
        'Время поиска на хосте не является измерением времени ответа на PicoCalc.','',
        '## Веса и воспроизведение','']
    m=report['models'][selected]
    lines +=[f"Выбранные веса: [{m['q4_bytes']} байт MKQ4v1]({m['q4_file']}); [HF checkpoint]({m['hf_directory']}).",'',
        'Контекст — 512 токенов; максимум три хода по 160 новых токенов. Q4-файл физически упакован '
        'и загружен перед проверкой. Активации и KV-кеш хоста — FP32. Нативный runtime PicoCalc, его скорость '
        'и пиковая память пока не измерены.','',
        'Локальная проверка харнесса:','',
        '```sh','python3 research/mk61-agent-20261106/repair_search_test.py','```','',
        'Для интерактивной пробы `try_model.py` принимает `--repair-budget 512`. '
        'Числовые примеры в JSON должны содержать ожидаемый результат. '
        'Полные ответы, скрытые проверки, хеши, источники данных и все веса находятся в '
        '`.build/mk61-agent-20261106/distill-hard/`.','']
    lines += ['В `demo-repair.json` описан запас ходов R2 и использованные ходы R0. '
        'Сохранённая Q4-модель трижды выдаёт сложение `62 60 10 50`; после семи проб харнесс получает '
        'вычитание `62 60 11 50`, проходящее все переданные проверки. Это иллюстрация из итогового набора, '
        'не дополнительный результат бенчмарка.','', '```sh',
        '.build/squeal-chat-20261105/venv/bin/python research/mk61-agent-20261106/try_model.py \\',
        '  --model .build/mk61-agent-20261106/distill-hard/export/baseline/hf \\',
        '  --weights .build/mk61-agent-20261106/distill-hard/export/baseline/model.mkq4 \\',
        '  --task-file research/mk61-agent-20261106/demo-repair.json \\',
        '  --no-plan --repair-budget 512', '```', '']
    (HERE/'FINAL_RESULTS.md').write_text('\n'.join(lines))
    print(json.dumps({'selected':selected,'neural_target_met':neural_target,'hybrid_target_met':hybrid_target,
         'neural_fresh':n,'neural_formal':f,'hybrid_fresh':h,'hybrid_formal':hf,'q4_bytes':m['q4_bytes']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
