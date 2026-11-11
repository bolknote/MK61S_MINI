"""Report both preselected Q4 branches, paired uncertainty and completion risk."""
import argparse
import collections
import json
import math
from pathlib import Path
import random
import statistics
from ay_common import HERE,write,sha
from ay_eval import primary_metrics,episode_metrics
from ay_codec import UNARY_NAMES,BINARY_NAMES
from ay_data import op_count


def paired(a,b):
    a={r['id']:r for r in a};b={r['id']:r for r in b};assert set(a)==set(b)
    values=[int(b[k]['program_correct'])-int(a[k]['program_correct'])for k in sorted(a)]
    rng=random.Random(26110807);n=len(values)
    samples=sorted(sum(rng.choices(values,k=n))/n for _ in range(6000))
    wins=sum(x==1 for x in values);losses=sum(x==-1 for x in values);discordant=wins+losses
    probability=min(1.,2*sum(math.comb(discordant,i)for i in range(min(wins,losses)+1))/(2**discordant))if discordant else 1.
    return {'total':n,'spec_only_correct':wins,'hex_only_correct':losses,'difference':statistics.mean(values),
            'paired_bootstrap_95':[samples[149],samples[5849]],'McNemar_exact_two_sided':probability}


def main(root):
    assert json.loads((root/'complete.json').read_text())['completed']
    reports={a:json.loads((root/a/'closed.json').read_text())for a in ['hex','spec']}
    baselines={a:json.loads((root/('source-'+a+'-closed.json')).read_text())for a in ['hex','spec']}
    choices=json.loads((root/'preselected.json').read_text());prepared=json.loads((root/'prepared.json').read_text())
    data=json.loads((root/'data-clean.json').read_text());policy=json.loads((root/'policy.json').read_text())
    assert not choices['closed_used_for_selection']
    for a in reports:assert(root/'preselected.json').stat().st_mtime<=(root/a/'closed.json').stat().st_mtime
    stats={'preselected':choices,'data':data['counts'],'trained':{},'source':{},'paired':{},'optimizer_updates':6000}
    for arm,r in reports.items():
        stats['trained'][arm]={name:x['summary']for name,x in r.items()if isinstance(x,dict)and'summary'in x}
        stats['source'][arm]={name:x['summary']for name,x in baselines[arm].items()if isinstance(x,dict)and'summary'in x}
        for gate in ['raw','self']:
            stats['trained'][arm][gate]['tool_or_compilation_errors']=sum(any(h['kind']=='error'for h in row['history'])for row in r[gate]['records'])
            stats['trained'][arm][gate]['correct_DONE_public_ineligible']=sum(row['finished']and row['program_correct']and not row['eligible']for row in r[gate]['records'])
    for panel in ['all','known','novel']:
        v={a:[r for r in reports[a]['primary']['records']if panel=='all'or r['panel']==panel]for a in reports}
        stats['paired'][panel]=paired(v['hex'],v['spec'])
    curves={}
    for arm in reports:
        curves[arm]=[]
        for step in policy['checkpoints']:
            r=json.loads((root/arm/f'development-{step}.json').read_text())
            curves[arm].append({'step':step,'primary':r['primary']['summary'],'panels':r['primary']['panels'],'raw':r['raw']['summary']})
    stats['development_curves']=curves
    shared={r['id']for r in reports['hex']['primary']['records']if r['program_correct']}&{r['id']for r in reports['spec']['primary']['records']if r['program_correct']}
    stats['same_successful_tasks_output_tokens']={'tasks':len(shared),**{a:statistics.mean(len(r['generation']['generated_token_ids'])for r in reports[a]['primary']['records']if r['id']in shared)for a in reports}}
    write(root/'comparison.json',stats)
    lines=['# 3M Q4: компактная спецификация против HEX', '',
      'Обе ветки дообучены от одного и того же Q4-состояния AQ full (шаг 2500). '
      'Меняется смысл байтов в WRITE: HEX — программа МК-61 с прежними макросами; '
      'SPEC — дерево выражения и один необязательный адрес записи результата. Дерево компилируется детерминированно. '
      'Во время экзамена DeepSeek не вызывалась.', '',
      'На закрытом наборе SPEC лучше в одношаговом переводе: 175/294 против 154/294 у дообученного HEX '
      '(исходный HEX: 28/294). Общая парная разность +7.1 п.п.; интервал по задачам +1.0 … +13.6 п.п. '
      'В интерактивном отладочном протоколе HEX заметно сильнее: 112/256 правильных завершений против 27/256. '
      'По сравнению с исходным HEX само дообучение улучшило завершение с 32/256 до 112/256, '
      'снизив ложные DONE со 140 до 28 при почти одинаковом числе DONE (172 и 174). '
      'Результат поддерживает дальнейшую работу над SPEC как переводчиком, но не замену им действующего отладочного агента.', '',
      'Это сравнение двух дообученных систем с одним исходным состоянием, а не оценка двух случайно инициализированных архитектур. '
      'Исходная сеть уже знала формат HEX; SPEC для неё новый язык вывода. '
      'Дерево не является свободным текстовым рассуждением и пока описывает только прямолинейную арифметику и запись результата, без циклов и ветвлений.', '',
      f'В каждом плече выполнено {policy["steps"]} обновлений, batch {policy["batch"]}, Q4 на каждом прямом проходе, вычисления и активации FP32. '
      f'Обновлялись свежие адаптеры rank16 и шесть строк действий, всего {prepared["trainable_parameters"]:,} коэффициентов. '
      'После слияния модель в обоих случаях имеет 3 022 080 параметров. Русские входные строки словаря и все тензоры вне адаптеров сохранены. '
      'Выборки, число шагов, функция потерь и начальные коэффициенты совпадают; штрафа DONE, DPO и нового нейросетевого критика нет.', '',
      'DeepSeek создавала русские перефразировки случайных деревьев и независимо восстанавливала по ним формулу. '
      'Обратная проверка не видела исходного AST. Совпадение проверено численно, программы эталонов — ROM. '
      'Метки WRITE/RUN/DONE/UNSURE получены через настоящие Session и эмулятор. '
      'Разные математические смыслы одного русского выражения и коррелированные ошибки учителя полностью исключить этим нельзя.', '',
      '| Набор после удаления повторов | Деревьев | Русских условий |','|---|---:|---:|']
    for split,d in data['counts'].items():lines.append(f'| {split} | {d["trees"]} | {d["questions"]} |')
    lines += ['', 'Удалены совпадения с учётом коммутативности +/* и несущественного углового режима, а также сигнатуры открытого пилота. '
      'Это не исчерпывающая проверка всех алгебраических тождеств. Новые сочетания удержаны из текущего обучения; '
      'они не объявляются отсутствовавшими во всей истории предыдущих этапов. '
      f'Учебных состояний {prepared["valid_lessons"]:,}; одинаково допустимых в обоих форматах — все, исключённых по длине: {sum(prepared["dropped_for_both"].values())}. '
      'Контроль и закрытый тест различаются также удержанными парами операций.', '',
      'Чекпойнты выбирались только на development, по минимуму качества known/novel, затем общему числу правильных программ '
      'и качеству завершения. После фиксации двух чекпойнтов закрытый тест открыт один раз для обеих веток и неизменённой исходной модели. '
      'На закрытом наборе веса и пороги не подбирались.', '',
      '| Ветка | Выбранный шаг |','|---|---:|']
    for arm,v in choices['choices'].items():lines.append(f'| {arm} | {v["step"]} |')
    lines += ['', 'В основной проверке запрашивается одна гипотеза WRITE; выбор действия принудительно фиксирован. '
      'Успех означает, что полученный код корректно исполняет исходное условие на отдельных аудиторских входах, '
      'включая сохранение неназванной памяти. Для SPEC дополнительно отдельно проверяются разбор дерева и его математический смысл. '
      'У HEX подразумеваемая формула восстанавливается частичным символьным декодером, поэтому её отсутствие не отменяет правильное исполнение кода.', '',
      '| Q4, одна попытка | Всего верно | Known | Удержанные сочетания | Ошибки формата/компиляции | Среднее токенов ответа |',
      '|---|---:|---:|---:|---:|---:|']
    for label,r in [('source HEX',baselines['hex']),('HEX после обучения',reports['hex']),('SPEC после обучения',reports['spec'])]:
        p=r['primary'];s=p['summary'];known=p['panels']['known'];novel=p['panels']['novel']
        lines.append(f'| {label} | {s["passed"]}/{s["total"]} | {known["passed"]}/{known["total"]} | {novel["passed"]}/{novel["total"]} | {s["codec_errors"]} | {s["mean_generated_tokens"]:.1f} |')
    lines += ['', 'Разность SPEC−HEX, парная выборка по задачам:', '',
      '| Панель | Только SPEC верна | Только HEX верна | Разность, п.п. | 95% парный bootstrap, п.п. |',
      '|---|---:|---:|---:|---:|---:|']
    for panel,p in stats['paired'].items():
        lo,hi=p['paired_bootstrap_95'];lines.append(f'| {panel} | {p["spec_only_correct"]} | {p["hex_only_correct"]} | {100*p["difference"]:+.1f} | {100*lo:+.1f} … {100*hi:+.1f} |')
    lines += ['', 'Интервалы отражают только разброс задач при одном общем seed обучения; разные seed не проверялись. '
      'Численные совпадения — конечные проверки с допуском 2e-6, не доказательство равенства произвольных программ.', '',
      f'На {len(shared)} задачах, правильно решённых обеими ветками, средний ответ HEX — '
      f'{stats["same_successful_tasks_output_tokens"]["hex"]:.1f} токена, SPEC — '
      f'{stats["same_successful_tasks_output_tokens"]["spec"]:.1f}. '
      'Общее среднее в таблице включает и неверные гипотезы. Оба нативных пакета имеют размер 2 160 856 байтов; '
      'сокращение вывода не освободило память весов.', '',
      'Пошаговый тест использует одинаковые 128 условий (по 64 из known/novel), правильный и ошибочный старт '
      'на каждое условие, реальные публичные факты, бюджет 12 действий. '
      'Raw принимает собственный DONE сети. Self дополнительно проверяет код против формальной гипотезы, '
      'сделанной отдельно до показа текущей программы. Эта гипотеза может неверно понимать запрос; '
      'её нельзя выдавать за независимо подтверждённую спецификацию.', '',
      'Текущая программа показывается обеим веткам в HEX. SPEC должна читать HEX и выдавать дерево; '
      'однородный семантический вход для неё здесь не проверялся. Это ограничение интерпретации отладочного теста. '
      'В одношаговой проверке текущей программы на входе нет.', '',
      '| Ветка / gate | Правильных завершений | Принято DONE | Ложных по запросу | Верный итоговый код | Исправлено и завершено плохих стартов |',
      '|---|---:|---:|---:|---:|---:|']
    m=baselines['hex']['raw']['summary']
    lines.append(f'| source HEX / raw | {m["passed"]}/{m["total"]} | {m["DONE"]} | {m["false_DONE"]} | {m["final_correct_code"]} | {m["wrong_starts_repaired"]}/{m["wrong_starts"]} |')
    for arm,r in reports.items():
        for gate in ['raw','self']:
            m=r[gate]['summary'];lines.append(f'| {arm} / {gate} | {m["passed"]}/{m["total"]} | {m["DONE"]} | {m["false_DONE"]} | {m["final_correct_code"]} | {m["wrong_starts_repaired"]}/{m["wrong_starts"]} |')
    lines += ['', '| Ветка / gate | UNSURE | Лимит/ошибка | Ошибки токенизации/генерации | Ошибки инструментов/компиляции | Переполнение контекста |',
      '|---|---:|---:|---:|---:|---:|']
    for arm in reports:
        for gate in ['raw','self']:
            m=stats['trained'][arm][gate]
            lines.append(f'| {arm} / {gate} | {m["abstained"]} | {m["exhausted"]} | {m["generation_errors"]} | {m["tool_or_compilation_errors"]} | {m["context_overflows"]} |')
    lines += ['', 'Дополнительно raw DONE на правильном по аудиту коде, но без успешной актуальной публичной проверки: '
      f'HEX — {stats["trained"]["hex"]["raw"]["correct_DONE_public_ineligible"]}, '
      f'SPEC — {stats["trained"]["spec"]["raw"]["correct_DONE_public_ineligible"]}. '
      'Они не включены в успешные завершения. В учебных RUN-целях этого этапа использовался только случай 01; '
      'переход к 00 после повторной правки требует отдельного покрытия следующего курса. '
      'Ошибки DONE следует читать вместе с количеством принятых ответов и отказов.', '',
      'Самосогласованность кода и собственной спецификации не доказывает понимание запроса. '
      'В компьютерном прототипе ax_completion.py такие случаи имеют статус «код проверен по неподтверждённой спецификации». '
      'Прикладной DONE требует независимо подтверждённой спецификации; во время этого исследования raw/self остаются диагностическими режимами.', '',
      'Обе ветки используют прежний русский словарь и тот же алфавит HEX-токенов. '
      'Генератор в обоих случаях ограничен одинаковым синтаксисом пар HEX-цифр; '
      'специальная грамматика дерева не помогает SPEC выбирать допустимую операцию. '
      'Префикс SPEC: FF либо 00..0E задаёт отсутствие/адрес записи, затем дерево; '
      '00..0E — входные регистры, 10 kk — индекс константы, 11 — pi, 20..31 — унарные операции, 40..44 — бинарные. '
      'Режим углов задаётся harness, как и у HEX. Ограничение программы — 105 ячеек стандартного МК-61.', '',
      'CPU-переэкспорт Q4, побитовое сохранение словаря и сравнение выбранных потоков B200 с CPU и переносимым C++-движком '
      'сохраняются в native-verification.json. Это проверка компьютерного исполнения. '
      'Скорость и память физического PicoCalc здесь не измерялись; прошивка и основной профиль модели не заменялись.', '',
      'Модели: `server-results/export/hex` и `server-results/export/spec`. '
      'Локальная проба: `.build/squeal-chat-20261105/venv/bin/python research/mk61-agent-20261106/ay_chat.py '
      '--model <папка export/hex или export/spec> --task "Вычисли квадрат R0" --angle DEG --inputs \'{"R0":"3"}\'`. '
      'Скрипт работает офлайн и показывает гипотезу, итоговый HEX и фактический результат; понимание условия помечено неподтверждённым.', '',
      'Полные данные, политики, начальные SHA, контрольные кривые, выбранные чекпойнты и экзамены находятся в '
      '`.build/mk61-agent-20261106/semantic-spec-distill-v1/`.']
    if(root/'user-regression.json').exists():
        lines += ['', 'Историческая пользовательская проба «синус 22°» проверена отдельно и не входит в новые 294 задачи. '
          'В этом корпусе у каждого выражения требовался хотя бы один входной регистр; чисто константных условий не было. '
          'Обе ветки эту пробу провалили: HEX выбрала sin(3), SPEC — sin(10^(10+R1)). '
          'Это существенное ограничение для обычного использования. Следующий корпус должен включать чистые константы, '
          'новые числа и выбор их индекса из таблицы, а также полные траектории RUN для обоих номеров случая. '
          'По этой пробе веса текущего эксперимента не исправлялись; следующему обучению потребуется новый закрытый тест.']
    lines += ['', 'Экспорт содержит wire-format.json с обязательной политикой таблицы констант. '
      'База одинакова у обеих веток и содержит 12 значений; дополнительные числа добавляются в порядке извлечения из условия. '
      'При использовании этих весов harness должен применять данную политику и подходящий декодер WRITE. '
      'Пакеты не подменяли текущую прошивку или основной профиль модели.']
    (HERE/'SEMANTIC_SPEC_DISTILL_RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in stats.items()if k not in ['development_curves']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
