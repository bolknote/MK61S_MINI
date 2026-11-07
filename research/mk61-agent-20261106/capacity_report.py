"""Record completed controlled results without mixing the older harder audits."""
import json
from pathlib import Path

from tasks import BUILD


def main():
    root=BUILD/'capacity-v1/server-results';report=Path(__file__).parent/'FINAL_RESULTS.md'
    complete=json.loads((root/'complete.json').read_text());assert complete['completed']
    selected=json.loads((root/'preselected.json').read_text());assert selected['level']==1
    verification=json.loads((root/'local-verification.json').read_text())
    assert all(v['reload_max_error']==0 for v in verification['exports'].values())
    assert json.loads((root/'postflight.json').read_text())['all_own_jobs_complete']
    order=['small-q4-fresh','grown-q4-fresh','small-q3-qat-fresh','grown-q3-qat-fresh',
           'small-q2-qat-fresh','grown-q2-qat-fresh','small-mixed-qat-fresh','grown-mixed-qat-fresh']
    rows=[]
    for label in order:
        d=json.loads((root/'results'/(label+'.json')).read_text());m=d['summary']
        rows.append({'label':label,'parameters':d['packed']['parameters'],'bytes':d['packed']['bytes'],
          'manual_parse':m['manual']['parse']['passed'],'manual_program':m['manual']['program']['passed'],
          'manual_total':m['manual']['program']['total'],'teacher_program':m['teacher']['program']['passed'],
          'teacher_total':m['teacher']['program']['total'],'formal20':m['formal']['passed']})
    full={p.stem:json.loads(p.read_text())['passed']for p in(root/'full-formal').glob('*.json')}
    summary={'matrix':rows,'full_formal98':full,'selection_used_fresh':False,'single_operation_gate_met':False,
      'tests_passed':21,'verification':{k:v for k,v in verification.items()if k!='details'},
      'matched_training_steps_per_size':6000,'additional_qat_steps_per_precision_per_size':500,
      'new_completed_training_runs':10,'new_optimizer_updates_total':15000,
      'semantic_tasks_are_single_operation_only':True,'selected_export':'export/selected-budget',
      'native_device_runtime_measured':False}
    (root/'summary-local.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    lines=['<!-- capacity-v1 -->','', '## Новый курс, размер FFN и Q2/Q4 — 6 ноября 2026','',
      '**Выбрана 3M Q4: 60/84 новых одношаговых условий и 98/98 формальных задач.** '
      'В этой проверке увеличение одного FFN не улучшило качество. Смешанная 4,49M '
      'занимает близкий объём весов, но решает 50/84. Порог надёжности 90% не достигнут.','',
      'Эти 84 условия содержат по одной из семи операций. Они проще предыдущих '
      '64 условий с составными вычислениями; проценты разных выборок напрямую не сравниваются. '
      'Новый протокол скрывает числовые примеры и оценивает первую программу без починки. '
      'Прежний обученный checkpoint в том же протоколе решает 0/84.','',
      '| Параметры | Формат | Файл весов, МиБ | Разбор /84 | Программа /84 | Тексты учителя /98 |',
      '| --- | --- | ---: | ---: | ---: | ---: |']
    for r in rows:
        mode='Q2 FFN / Q4 остальное'if'mixed'in r['label']else r['label'].split('-')[1].upper()
        lines.append(f"| {r['parameters']:,} | {mode} | {r['bytes']/1024**2:.2f} | {r['manual_parse']} | {r['manual_program']} | {r['teacher_program']} |")
    lines+=['','Для Q3/Q2/смешанных форматов показаны выбранные по валидации снимки после '
      '500 шагов QAT. Обычное равномерное квантование по группам 32 весов — ограниченный '
      'базовый рецепт. Прямое округление до Q2/смешанного формата дало 0/84 программ; '
      'адаптация восстановила часть навыка. Это не оценка предела двухбитных сетей или '
      'полного обучения модели в смешанной точности. '
      'Работа [ParetoQ](https://arxiv.org/abs/2502.02631) также рассматривает '
      'адаптацию к малой битности как отдельную задачу; её алгоритм здесь не воспроизводился.','',
      'Сравнение FP32/Q4 у выбранной 3M: 59/84 и 60/84 программ. У 4,49M: 59/84 и 58/84. '
      'Увеличение точности до FP32 этот языковой барьер не убрало. На полном старом '
      f"формальном наборе 3M Q4 — {full['small-primary']}/98, 4,49M Q4 — {full['grown-primary']}/98.",'',
      'От соседнего опыта `LLM на PicoCalc` заимствованы предсказание короткого '
      '`<calc>` перед байтами, близкие условия с разными действиями, одинаковое '
      'взвешивание коротких/длинных ответов и сохранение результата на худшей '
      'валидационной группе. Префикс выводит сама сеть. Компилятор не пишет за неё '
      'программу при оценке. Это структурированный промежуточный результат; '
      'универсальные многошаговые рассуждения не установлены.','',
      'Новый корпус: 7 587 разных учебных описаний, 928 валидационных и 934 тестовых. '
      'Каждое сохранённое описание прошло отдельный обратный разбор, эталон исполнялся '
      'на микрокодном ядре. Происхождение минимальных пар и совпадающие тексты с '
      'переименованными регистрами не пересекают части данных. Идентификаторы '
      'проверяющего обезличены, классы перемешаны. Первая проверка с названиями операций '
      'в служебных ID исключена до градиентов; запросы сохранены для аудита.','',
      'Оба размера получили по 4 000 одинаковых обновлений, затем по 2 000 с '
      '30% старых арифметических и управляющих заданий. Исходное повторение только '
      'управляющих задач привело к забыванию составных формул; полный replay вернул '
      'формальную точность. Квантование адаптировалось по 500 шагов для каждого '
      'из трёх форматов и двух размеров. Всего 15 000 новых обновлений в 10 запусках. '
      'Итоговая выборка не выбирала снимки, форматы или длительность обучения. '
      'Курса из двух операций не было: установленный порог первого курса не пройден.','',
      f"Все пять экспортов восстановились с ошибкой 0. На CPU совпали {verification['cpu_b200_reply_matches']}/"
      f"{verification['compared']} ответов с B200. Фактическое хранение KV в FP16 проверено: "
      f"совпали {verification['fp16_fp32_reply_matches']}/{verification['compared']} ответов; размер "
      'хранимых тензоров соответствует формуле. Это выборочные проверки на хосте, '
      'где арифметика внимания остаётся FP32. Нативный запуск этих экспортов на '
      'PicoCalc и пиковая память устройства не измерены. 21 техническая проверка прошла.','',
      '[Выбранные веса](/Users/bolk/Projects/MK61S_MINI/.build/mk61-agent-20261106/capacity-v1/server-results/export/selected-budget/model.mkq4) · '
      '[Итоговые метрики](/Users/bolk/Projects/MK61S_MINI/.build/mk61-agent-20261106/capacity-v1/server-results/summary-local.json) · '
      '[Проверка CPU и KV](/Users/bolk/Projects/MK61S_MINI/.build/mk61-agent-20261106/capacity-v1/server-results/local-verification.json)','',
      'Схема следующего, ещё не обученного сравнения: скрытая ширина 256, 10 слоёв, '
      '8 Q-голов и 1 KV-голова. Q4 с FFN288 содержит 5 789 568 параметров и '
      '3 277 312 байт весового payload; Q2-FFN/Q4-остальное с FFN512 содержит '
      '7 509 888 параметров и 3 261 952 байт. Шкалы включены, заголовок и рабочие '
      'буферы исключены. KV FP16 — 1,25 МиБ для 1024 или 2,5 МиБ для 2048 токенов. '
      'Это расчёт архитектуры, а не измеренное качество или готовый runtime. '
      '[Точный расчёт](/Users/bolk/Projects/MK61S_MINI/.build/mk61-agent-20261106/capacity-v1/proposed-mixed-design/design.json).','']
    old=report.read_text().split('<!-- capacity-v1 -->')[0].rstrip()
    report.write_text(old+'\n\n'+'\n'.join(lines))
    print(json.dumps({'report':str(report),'rows':len(rows),'full_formal':full},ensure_ascii=False))


if __name__=='__main__':main()
