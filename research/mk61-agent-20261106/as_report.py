"""Consolidate the completed diagnostics without changing weights or policies."""
import collections
import json
import statistics
from ar_common import REPO,HERE,read,write,sha
from ar_report import metrics,interval
from ar_spec import spec_text
from ha_protocol import bytes_text

BASE=REPO/'.build/mk61-agent-20261106'


def cells(records):
    return {mode+':'+gate:metrics([r for r in records if r['input_mode']==mode and r['gate']==gate])
            for mode in ['natural','formal']for gate in ['raw','mechanical']}


def main():
    first=read(BASE/'spec-diagnostic-v1/summary.json')
    native={actor:read(BASE/'spec-diagnostic-native-v1/server-results'/actor/'results.json')for actor in ['small','teacher']}
    dsroot=BASE/'spec-diagnostic-deepseek-v1';ds=read(dsroot/'teacher/results.json')
    translation=read(dsroot/'translation.json')['records']
    replay=read(BASE/'spec-diagnostic-teacher-spec-v1/server-results/results.json')
    small_cells=cells(native['small']['records']);qwen_cells=cells(native['teacher']['records']);ds_cells=cells(ds['records'])
    replay_cells={g:metrics([r for r in replay['records']if r['gate']==g])for g in ['raw','mechanical']}
    original={r['id']:r for r in native['small']['records']if r['input_mode']=='natural'and r['gate']=='raw'}
    repeated={r['id']:r for r in replay['records']if r['gate']=='raw'}
    assert set(original)==set(repeated)
    action_stream=lambda r:[(h.get('generation',{}).get('action'),h.get('generation',{}).get('body'))for h in r['history']]
    same=sum(action_stream(original[k])==action_stream(repeated[k])for k in original)
    pairs={r['id'].rsplit(':',1)[0]:r for r in replay['records']if r['gate']=='raw'}
    other={r['id'].rsplit(':',1)[0]:r for r in replay['records']if r['gate']=='mechanical'}
    changes={}
    for field in ['solved','false_DONE']:
        by_goal=collections.defaultdict(list)
        for key,a in pairs.items():
            b=other[key];f=lambda r:int(r['pass'])if field=='solved'else int(r['finished']and not r['task_correct'])
            by_goal[a['task_id']].append(f(b)-f(a))
        values=[statistics.mean(x)for x in by_goal.values()]
        changes[field]={'delta':statistics.mean(values),'cluster_bootstrap_95':interval(values),'clusters':32}
    tr={'total':len(translation),'intent_correct':sum(r['intent']['tested_equal']for r in translation),
        'compiled_spec_pass':sum(r['implementation_audit']['status']=='TESTED'for r in translation),
        'compiled_task_pass':sum(r['task_audit']['status']=='TESTED'for r in translation)}
    plans={}
    for label,result in [('small',native['small']),('DeepSeek',ds)]:
        plans[label]={}
        for mode in ['natural','formal']:
            rows=[r for r in result['plans']if r['mode']==mode]
            plans[label][mode]={'total':len(rows),'spec_available':sum(r['spec']is not None for r in rows),
                               'goal_only_code_correct':sum(r['program_to_task']['status']=='TESTED'for r in rows),
                               'implied_spec_correct':sum(r['intent']['tested_equal']for r in rows)}
    examples=[]
    for r in native['small']['records']:
        if r['input_mode']=='natural'and r['gate']=='mechanical'and r['finished']and not r['task_correct']:
            examples.append({'tag':'wrong_self_spec_accepted','id':r['id'],'task':r['task'],'spec':r['declared_spec'],
                             'HEX':r['body'],'counterexample_to_task':r['task_audit']})
            if len(examples)==2:break
    for r in replay['records']:
        if r['gate']=='mechanical'and any(x['status']=='FAIL'for x in r['gate_checks']):
            examples.append({'tag':'teacher_spec_rejects','id':r['id'],'task':r['task'],'spec':r['declared_spec'],
                             'checks':r['gate_checks'],'final_status':'DONE'if r['finished']else'UNSURE'})
            break
    stats={'small_native':small_cells,'Qwen_native_without_reference':qwen_cells,'DeepSeek_with_reference':ds_cells,
           'small_with_independent_spec':replay_cells,'semantic_translation':tr,'goal_only_plans':plans,
           'raw_replay_exact_action_stream_matches':same,'raw_replay_total':64,'paired_changes':changes,
           'episodes_completed':1408,'optimizer_updates':0}
    write(BASE/'spec-diagnostic-teacher-spec-v1/comparison.json',stats)
    write(BASE/'spec-diagnostic-teacher-spec-v1/selected-examples.json',examples)
    lines=['# Механическая проверка, формальные спецификации и DeepSeek', '',
      'На этом этапе веса не обучались и не заменялись. Проверяющий действительно выполняет программы на ROM МК-61; '
      'его ответы не являются оценкой нейросетевого критика. Главный результат: независимая правильная спецификация '
      'убрала 37 ложных DONE у неизменённой 3M, сохранив все 14 правильных завершений на 64 диагностических эпизодах.', '',
      '32 условия × правильный/неверный старт дают 64 эпизода на строку. Это 32 группы наблюдений, а не 64 независимых задачи. '
      'Есть унарные, бинарные, составные вычисления и записи в память; ветвлений и циклов нет. '
      'В каждом эпизоде до 12 действий. Актор видит только исходную задачу, текущий код и реальные публичные факты. '
      'После изменения кода прежние публичные результаты аннулируются. Порог/веса по этому набору не выбирались.', '',
      '| 3M Q4, обычный русский запрос | Правильных завершений | Принято DONE | Ложных DONE по исходной задаче |',
      '|---|---:|---:|---:|']
    for label,m in [('Без проверки смысла',small_cells['natural:raw']),
                    ('Проверка по собственной формальной гипотезе',small_cells['natural:mechanical']),
                    ('Проверка по независимой формуле DeepSeek',replay_cells['mechanical'])]:
        lines.append(f'| {label} | {m["solved"]}/64 | {m["DONE"]} | {m["false_DONE_task"]} |')
    lines += ['', f'При замене поставщика спецификации {same}/64 контрольных raw-потоков действий и HEX совпали целиком '
      'с предыдущим запуском. Начальный промпт маленькой модели не содержит формулу учителя и не менялся. '
      'Спецификация находится у механического проверяющего; актор получает только контрпример к ней после отклонённого DONE. '
      'Скрытые ответы исходной задачи актору и runtime в natural не передаются.', '',
      'В варианте с формулой DeepSeek итоговый правильный код остался в 17/64 эпизодах, а завершение осталось правильным в 14/64. '
      'Проверка изменила принятие результата, а не способность модели исправлять программу: '
      f'успешных исправлений неверного старта {replay_cells["raw"]["wrong_starts_repaired"]}/32 до и '
      f'{replay_cells["mechanical"]["wrong_starts_repaired"]}/32 после. '
      f'UNSURE вырос с {replay_cells["raw"]["abstained"]} до {replay_cells["mechanical"]["abstained"]}; '
      'ошибок генерации и переполнений контекста в этом контроле нет.', '',
      'Собственная гипотеза получена из goal-only HEX, сгенерированного до показа текущей программы, '
      'и восстановлена консервативным символьным декодером. Это проверка цепочки «условие → собственный код → подразумеваемая формула», '
      'а не чистая оценка понимания русского языка. У 3M такая гипотеза была доступна для 29/32 условий; '
      'с исходной задачей совпала для 6/32. Именно поэтому проверка по ней может принять неправильное решение '
      'и отклонить правильное. При неподдерживаемом коде гипотеза остаётся неизвестной, эталон её не заменяет.', '',
      f'Парное снижение доли ложных DONE с независимой спецификацией: {100*changes["false_DONE"]["delta"]:.1f} п.п.; '
      f'95% bootstrap-интервал по 32 условиям: {100*changes["false_DONE"]["cluster_bootstrap_95"][0]:.1f} … '
      f'{100*changes["false_DONE"]["cluster_bootstrap_95"][1]:.1f} п.п. '
      'Это неопределённость малого диагностического набора, не гарантия нуля ошибок на новых задачах.', '',
      'DeepSeek V4.1 Flash (так модель называется в доступном API) использовалась в двух разных ролях. '
      'В переводе русского условия в ограниченную формулу не требовались HEX или знание МК-61:', '',
      '| Отдельный переводчик DeepSeek | Результат |','|---|---:|',
      f'| Формула и требуемые записи совпали с исходным условием | {tr["intent_correct"]}/32 |',
      f'| Детерминированно собранный код прошёл проверку своей спецификации | {tr["compiled_spec_pass"]}/32 |',
      f'| Тот же код прошёл независимую проверку исходной задачи | {tr["compiled_task_pass"]}/32 |', '',
      'Это гибрид «большой переводчик → компилятор → эмулятор», отдельно от работы 3M и её DONE. '
      'Он пока не является автономным агентом на PicoCalc: большая модель нужна здесь как исследовательский учитель. '
      'Результат относится только к данным 32 задачам. Правильность перевода проверена офлайн, '
      'а в произвольной новой задаче формула учителя также остаётся гипотезой.', '',
      'В роли агента DeepSeek получила тот же снимок сессии и действия, а также отдельный справочник кодов. '
      'Это проверка протокола, не равное сравнение без справочника. Число ходов и факты эмулятора совпадают:', '',
      '| DeepSeek, исходный протокол | Правильный итоговый код | Принято DONE | Повторные действия до лимита |',
      '|---|---:|---:|---:|']
    for mode in ['natural','formal']:
        m=ds_cells[mode+':raw'];lines.append(f'| {mode} | {m["correct_code"]}/64 | {m["DONE"]} | {m["exhausted"]}/64 |')
    lines += ['', 'Во всех этих 256 эпизодах DeepSeek повторяла WRITE и не вызвала DONE. '
      'Ноль ложных DONE здесь означает нулевое покрытие, а не надёжность. '
      'В двух дополнительных задачах вне набора явное описание продолжения сессии дало DONE '
      'для обоих правильных стартов, но также ложный DONE для одного из двух неверных стартов. '
      'Например, при просьбе R7−R8 программа `68 67 11 50` вычисляла R8−R7; '
      'учитель принял её после такого уточнения протокола. Эти четыре первых решения не являются полноценным экзаменом. '
      'Они показывают, что выбор DONE чувствителен к протоколу и не заменяет внешней проверки.', '',
      'Проверяющий использует обычный математический вычислитель и фактическое состояние ROM. '
      'Проверяются останов, X, изменения памяти, сохранение остальных регистров и режим углов. '
      'Есть 24 проверочных входа и отдельные 32 аудиторских входа; проверены граничные значения и случайные внутренние точки '
      'в зафиксированных областях определения. Допуск 2e-6 абсолютный/относительный. '
      'TESTED означает конечные тесты, не математическое доказательство. '
      'Символьный декодер поддерживает только оговорённые прямолинейные формы; неподдерживаемое и ошибки области дают UNKNOWN.', '',
      'Для компьютерного прототипа добавлена политика завершения в `ax_completion.py`: '
      'совпадение кода с неподтверждённой собственной или учительской формулой даёт '
      '`CODE_TESTED_AGAINST_UNCONFIRMED_SPEC`, а не разрешение завершить исходную задачу. '
      'Подтверждение спецификации поступает от harness отдельно от текста модели. '
      'Для принятия дополнительно нужны актуальные публичные исполнения и успешные численные проверки. '
      'Пять случаев этой политики проверены, включая самосогласованную неправильную формулу.', '',
      'Первый пилот сохранён отдельно в `SPEC_DIAGNOSTIC_RESULTS.md`. Он добавлял формальную гипотезу во вход '
      'и использовал длинные контрпримеры; это ухудшало чтение условия маленькой сетью и приводило к переполнению 1024 токенов. '
      'Поэтому выполнен отдельный контроль с исходным AQ-промптом: 192 посимвольных сравнения прошли, '
      'в начальных снимках 704–863 токена. Набор при этом уже был открыт: этот контроль нельзя называть новым финальным тестом. '
      'Qwen без справочника плохо формировала HEX и давала незавершённые ответы; её нулевые гипотезы '
      'не трактуются как оценка общего интеллекта или доказательство превосходства другой архитектуры. '
      'В отдельном префлайте Qwen со справочником правильно решила 1/2 задач: во втором ответе '
      'перезаписала неназванные R0 и R1. Полный прогон этого варианта не запускался; '
      'оба ответа и неудачный префлайт сохранены в spec-diagnostic-reference-v1. '
      'Небольшая проблема параллельной записи одинаковых запросов в кеш исправлена отдельной транспортной обёрткой; '
      'замороженные промпты, веса и HTTP-параметры старых прогонов не менялись.', '',
      'Следующий учебный эксперимент:', '',
      '1. Отдельно обучать перевод русского условия в компактное дерево выражения и требуемых изменений состояния. '
      'Сравнить такую цель с прежним HEX на одинаковых 3M, данных и бюджете; преимущество новой формы пока не доказано.',
      '2. Генерировать составные деревья, проверять компиляцию ROM и получать от учителя русские формулировки. '
      'Проверять обратный перевод; удерживать в тесте сами сочетания операций и структуры деревьев, а не только слова. '
      'Не переносить нынешние 32 задачи в новый финальный тест.',
      '3. Учить переходы WRITE → недостающие RUN → проверка → исправление/UNSURE. '
      'DONE в учебных траекториях давать только после реальной проверки подтверждённой спецификации. '
      'Самооценку большой LLM не использовать как метку истины.',
      '4. Отдельно считать исходную генерацию, правильный код после исправления, корректное завершение и риск среди принятых ответов. '
      'На новом закрытом тесте проверять Q4, покрытие и интервалы по независимым задачам.', '',
      'В сумме завершено 1408 диагностических эпизодов, без единого обновления оптимизатора. '
      'Градиенты, прошивка и основной профиль модели не менялись; устройство не подключалось. '
      'Большая модель не заменяет локальную 3M: она дала проверенные семантические цели для следующего этапа.', '',
      'Артефакты находятся в `.build/mk61-agent-20261106/`: `spec-diagnostic-v1`, '
      '`spec-diagnostic-native-v1`, `spec-diagnostic-deepseek-v1`, `spec-diagnostic-teacher-spec-v1`. '
      'В них сохранены политики, SHA исходников и модели, все промпты, ответы, трассы и аудиторские контрпримеры.']
    for example in examples[:2]:
        lines += ['', f'Пример самосогласованной ошибки `{example["id"]}`: '+example['task'],
                  'Гипотеза: `'+spec_text(example['spec'])+'`. HEX: `'+bytes_text(example['HEX'])+'`.']
    (HERE/'SPEC_CHECKER_RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'translation':tr,'3M_independent_spec':replay_cells,'raw_action_stream_matches':same,
                      'completed_episodes':1408},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
