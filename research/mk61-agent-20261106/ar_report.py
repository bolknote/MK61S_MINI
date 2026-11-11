"""Postprocessing only: no model selection, source changes or further gradients."""
import collections
import json
import random
import statistics
from ar_common import ROOT, HERE, REPO, read, write, sha
from ar_spec import spec_text
from ha_protocol import bytes_text


def metrics(rows):
    done=[r for r in rows if r['finished']]
    good=[r for r in rows if r['initial']=='correct'];bad=[r for r in rows if r['initial']=='wrong']
    return {'total':len(rows),'solved':sum(r['pass']for r in rows),
            'DONE':len(done),'false_DONE_task':sum(not r['task_correct']for r in done),
            'false_DONE_spec':sum(not r['spec_consistent']for r in done),
            'wrong_intent_DONE':sum(not r['declared_intent']['tested_equal']for r in done),
            'correct_code':sum(r['task_correct']for r in rows),
            'spec_consistent_code':sum(r['spec_consistent']for r in rows),
            'spec_available':sum(r['spec_available']for r in rows),
            'correct_intent':sum(r['declared_intent']['tested_equal']for r in rows),
            'correct_starts':len(good),'correct_starts_completed':sum(r['pass']for r in good),
            'correct_starts_corrupted':sum(not r['task_correct']for r in good),
            'wrong_starts':len(bad),'wrong_starts_repaired':sum(r['pass']for r in bad),
            'abstained':sum(r['abstained']for r in rows),
            'exhausted':sum(not r['finished']and not r['abstained']for r in rows),
            'generation_errors':sum(any(h['kind']=='generation_error'for h in r['history'])for r in rows),
            'context_overflows':sum(any(h.get('generation',{}).get('codec_error')=='context_overflow'for h in r['history'])for r in rows),
            'gate_rejected_episodes':sum(any(c['status']!='TESTED'for c in r['gate_checks'])for r in rows),
            'gate_checks':sum(len(r['gate_checks'])for r in rows),
            'mean_turns':statistics.mean(len(r['history'])for r in rows)}


def interval(values):
    rng=random.Random(260009);n=len(values)
    estimates=sorted(sum(rng.choices(values,k=n))/n for _ in range(5000))
    return [estimates[124],estimates[4874]]


def main():
    results={label:read(ROOT/'server-results'/label/'results.json')for label in ['small','teacher']}
    goals=read(ROOT/'goals.json');summary={};examples=[];deltas={};curves={}
    for label,result in results.items():
        records=result['records'];assert len(records)==256
        assert len({r['id']for r in records})==256
        assert result['source_frozen_sha256']==sha(ROOT/'frozen.json')
        plans=result['plans'];summary[label]={'seconds':result['seconds'],'plans':{},'cells':{},'families':{}}
        for mode in ['natural','formal']:
            p=[r for r in plans if r['mode']==mode]
            summary[label]['plans'][mode]={'total':len(p),'spec_available':sum(r['spec']is not None for r in p),
                  'intent_correct':sum(r['intent']['tested_equal']for r in p),
                  'generated_program_correct':sum(r['program_to_task']['status']=='TESTED'for r in p),
                  'unavailable_reasons':dict(collections.Counter(r['inference_error']for r in p if r['spec']is None))}
            for gate in ['raw','mechanical']:
                rows=[r for r in records if r['input_mode']==mode and r['gate']==gate]
                m=metrics(rows);summary[label]['cells'][mode+':'+gate]=m
                for family in sorted({g['family']for g in goals}):
                    summary[label]['families'][mode+':'+gate+':'+family]=metrics([r for r in rows if r['family']==family])
            raw={r['id'].rsplit(':',1)[0]:r for r in records if r['input_mode']==mode and r['gate']=='raw'}
            mech={r['id'].rsplit(':',1)[0]:r for r in records if r['input_mode']==mode and r['gate']=='mechanical'}
            assert set(raw)==set(mech)
            for outcome in ['solved','false_DONE_task']:
                by_goal=collections.defaultdict(list)
                for key,a in raw.items():
                    b=mech[key]
                    f=lambda r:int(r['pass'])if outcome=='solved'else int(r['finished']and not r['task_correct'])
                    by_goal[a['task_id']].append(f(b)-f(a))
                vals=[statistics.mean(x)for x in by_goal.values()]
                deltas[label+':'+mode+':'+outcome]={'change_proportion':statistics.mean(vals),'cluster_bootstrap_95':interval(vals),'clusters':len(vals)}
        for r in records:
            tags=[]
            if r['finished']and not r['task_correct']and r['spec_consistent']:tags.append('self_consistent_wrong_intent')
            if r['gate']=='mechanical'and r['pass']and any(c['status']=='FAIL'for c in r['gate_checks']):tags.append('repaired_after_rejection')
            if r['gate']=='raw'and r['finished']and not r['task_correct']:tags.append('raw_false_DONE')
            for tag in tags:
                if sum(x['label']==label and x['tag']==tag for x in examples)<3:
                    examples.append({'label':label,'tag':tag,**r})
        if label=='small':
            for mode in ['natural','formal']:
                rows=[r for r in records if r['input_mode']==mode and r['gate']=='raw']
                values=[]
                for threshold in [None,-2,-1,0,1,2]:
                    accepted=[]
                    for r in rows:
                        if not r['finished']:continue
                        score=next((h.get('generation',{}).get('correctness_margin')for h in reversed(r['history'])if h['kind']=='done'),None)
                        if threshold is None or(score is not None and score>=threshold):accepted.append(r)
                    values.append({'threshold':threshold,'accepted':len(accepted),'correct':sum(r['task_correct']for r in accepted),
                                   'errors':sum(not r['task_correct']for r in accepted),'total':len(rows)})
                curves[mode]=values
    write(ROOT/'summary.json',{'models':summary,'paired_changes':deltas,'descriptive_margin_curve':curves})
    write(ROOT/'examples.json',examples)
    lines=['# Проверка формальной гипотезы и DONE: диагностический пилот',
           '', 'Сравнение выполнено без дообучения и без замены выбранной модели. '
           'Текущая 3M Q4 (AQ full, шаг 2500) и Qwen3.8-Flash-Next-FP8 получили одинаковые задачи, '
           'начальные программы, публичные факты эмулятора и шесть действий. Большой учитель работал без thinking; '
           'JSON служил только транспортом действия, маленькая сеть использовала прежние строки действий и HEX.',
           '', 'До первых ответов зафиксированы 32 задачи, по одной правильной и одной неверной стартовой программе, '
           'два вида условия и два режима DONE: 256 эпизодов на модель, всего 512. '
           'На каждый набор из 64 эпизодов приходится 32 независимых условия; повторения одного условия не считаются отдельными независимыми задачами. '
           'Это диагностический набор знакомых арифметических операций и их композиций, а не доказательство отсутствия пересечений со всей историей обучения.',
           '', 'В natural формальная гипотеза восстановлена символическим декодером из отдельного goal-only WRITE, '
           'полученного до показа текущей программы. Это подразумеваемая спецификация того же генератора, '
           'а не независимое мнение о смысле русского запроса. Если декодер не поддерживает код или его формула '
           'не выдерживает проверки собственной программы на ROM, гипотеза недоступна; эталон её не заменяет. '
           'В formal проверенная спецификация независимо дана как само условие. '
           'В обоих случаях raw и mechanical видят одну и ту же формальную гипотезу.',
           '', 'Mechanical разрешает DONE после запусков всех открытых случаев и проверки программы против объявленной '
           'спецификации на 24 входах. Проверяются X, указанные записи и сохранение остальных 15 регистров памяти, '
           'режим углов, останов и конечность чисел. Поддержаны однократные арифметические вычисления и записи в память; '
           'полноценные ветвления, циклы и продолжение после С/П пока не входят в спецификацию пилота. '
           'Дополнительные 32 входа используются только при финальном аудите и не сообщаются агенту. '
           'TESTED означает конечные численные проверки с допуском 2e-6, не математическое доказательство.',
           '', 'Области определения входов заданы профилями в goals.json. В них есть границы и случайные значения; '
           'стек и все регистры инициализированы, неназванная память содержит ненулевые значения. '
           'Символьный декодер прошёл 604 дифференциальных проверки против ROM и негативные тесты. '
           'Эталоны 32 задач прошли ещё 1856 запусков. Результаты проверки всегда относятся к заданной области и допуску.',
           '', '| Модель / условие | Формула доступна | Формула верна запросу | Goal-only код решает задачу |',
           '|---|---:|---:|---:|']
    for label in summary:
        for mode,p in summary[label]['plans'].items():
            lines.append(f'| {label} / {mode} | {p["spec_available"]}/32 | {p["intent_correct"]}/32 | {p["generated_program_correct"]}/32 |')
    lines += ['', 'Для formal колонка о goal-only формуле оценивает попытку сети прочитать данное формальное условие. '
              'Сам механический gate в formal всегда получает независимо заданную спецификацию, а не эту попытку.',
              '', '| Модель / условие / DONE | Решено | Принято DONE | Ложных относительно запроса | Ложных относительно спецификации | Исправлено неверных стартов |',
              '|---|---:|---:|---:|---:|---:|']
    for label in summary:
        for cell,m in summary[label]['cells'].items():
            lines.append(f'| {label} / {cell} | {m["solved"]}/64 | {m["DONE"]} | {m["false_DONE_task"]} | {m["false_DONE_spec"]} | {m["wrong_starts_repaired"]}/32 |')
    lines += ['', '«Решено» требует правильного кода на финальных входах, актуальных публичных запусков и принятого DONE. '
              'Количество принятых DONE показывает цену отказов: ноль ошибок при нуле ответов не является успехом.',
              '', '| Модель / условие | Отказы UNSURE | Незавершённые | Ошибки генерации / переполнение контекста | Отклонён DONE хотя бы раз |',
              '|---|---:|---:|---:|---:|']
    for label in summary:
        for cell,m in summary[label]['cells'].items():
            lines.append(f'| {label} / {cell} | {m["abstained"]} | {m["exhausted"]} | {m["generation_errors"]} / {m["context_overflows"]} | {m["gate_rejected_episodes"]} |')
    lines += ['', 'Парные изменения (mechanical минус raw); интервалы получены повторной выборкой 32 условий, '
              'сохраняя вместе два старта каждого условия. Это оценка неопределённости этого малого пилота.',
              '', '| Модель / условие / метрика | Изменение, п.п. | 95% интервал, п.п. |','|---|---:|---:|']
    for key,v in deltas.items():
        a,b=v['cluster_bootstrap_95'];lines.append(f'| {key} | {100*v["change_proportion"]:+.1f} | {100*a:+.1f} … {100*b:+.1f} |')
    lines += ['', 'Описательная кривая отсечения raw DONE по нейросетевому margin, без подбора порога и без повторного запуска. '
              'Margin не является калиброванной вероятностью.', '', '| Условие | Порог | Принято / 64 | Верно | Ошибок |','|---|---:|---:|---:|---:|']
    for mode,values in curves.items():
        for r in values:lines.append(f'| {mode} | {r["threshold"]if r["threshold"]is not None else"все"} | {r["accepted"]} | {r["correct"]} | {r["errors"]} |')
    lines += ['', 'Примеры (полные запросы, вызовы, контрпримеры и ответы сохранены в examples.json):']
    for r in examples:
        if sum(1 for x in examples[:examples.index(r)]if x['label']==r['label']and x['tag']==r['tag'])>0:continue
        lines += ['', f'- {r["label"]}, {r["tag"]}, `{r["id"]}`: {r["task"]}',
                  '  Гипотеза: `'+spec_text(r['declared_spec'])+'`. Итоговый HEX: `'+bytes_text(r['body']or[])+'`.']
    lines += ['', 'Технические ограничения сравнения: одинаковы смысл действий, доступные факты и бюджет 12 действий. '
              'Различаются сериализация ответа и токенизаторы. У маленькой модели окно 1024, у учителя серверное окно 8192; '
              'в модель передаётся только текущий снимок, без скрытого длинного диалога. '
              'Превышения окна и ошибки формата перечислены отдельно. Учитель ограничен 512 токенами ответа, '
              'thinking выключен. Этот тест одного режима учителя не устанавливает потолок его способностей '
              'и сам по себе не позволяет приписать каждую его ошибку протоколу.',
              '', 'Использована прежняя реализация исполнителя, проверяющего фактическое состояние ROM. '
              'На PicoCalc код не переносился, скорость на устройстве не измерялась. '
              'Ни один результат этого пилота не использован для выбора весов, обучения или порога. '
              'Для следующего обучения потребуются отдельные учебные траектории и новый закрытый финальный тест.',
              '', 'Артефакты: `.build/mk61-agent-20261106/spec-diagnostic-v1/{frozen.json,policy.json,goals.json,summary.json,examples.json,server-results/}`. '
              'SHA исходников, данных и Q4-пакета зафиксированы до генерации; полные ответы и HTTP-параметры учителя сохранены.']
    (HERE/'SPEC_DIAGNOSTIC_RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
