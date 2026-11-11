"""Compact public state and an explicitly untrusted, executed model hypothesis."""
import copy
import hashlib
import json
from decimal import Decimal
from ha_protocol import bytes_text, pool_text
from hf_runtime import input_bank
from ac_runtime import Session


def key(view, pool):
    payload = [view['task'], view['angle'], pool, [c['segments'] for c in view['public_tests']]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def goal_prompt(view, pool):
    return (f'МК-61: {view["angle"]}; 105 ячеек. HEX+макросы FF01kk=константа kk.\n'
        'Константы: '+pool_text(pool)+'\nЗадача: '+view['task']+'\n'
        'Составь гипотезу решения: полный HEX программы, результат в X. Это план, ещё не проверенный по условию.\nАссистент: <')


def code_prompt(view, pool, body):
    return (f'МК-61: {view["angle"]}.\nКонстанты: '+pool_text(pool)+'\n'
        'Программа HEX: '+bytes_text(body)+'\nОпредели вычисляемую операцию и источник аргумента по этому коду.\nАссистент: <')


def snapshot(s):
    return {'view': s.task, 'pool': list(s.pool), 'body': list(s.body or []), 'runs': copy.deepcopy(s.runs),
        'case': s.case, 'revision': s.revision, 'remaining': 10-(len(s.history)-getattr(s, 'initial_history', 0)),
        'observation': s.observation}


def execute_hypothesis(view, pool, generation, vm):
    result = {'body': list(generation.get('body', [])), 'generation': generation, 'runs': {}}
    if generation.get('codec_error') or generation.get('action') != 'write':
        result['error'] = 'План не сформирован'; return result
    try:
        s = Session({**view, 'constants': pool}, 'asm', body=result['body'], vm=vm, gate=False)
        for i in range(len(view['public_tests'])): s.run(i)
        result['runs'] = copy.deepcopy(s.runs)
    except (ValueError, ArithmeticError, RuntimeError) as e:
        result['error'] = type(e).__name__
    return result


def hypothesis_text(plan, current_runs):
    if plan is None: return ''
    if plan.get('error'): return 'Гипотеза модели недоступна: '+plan['error']+'.\n'
    lines = ['Гипотеза модели HEX: '+bytes_text(plan['body'])+'. Это не эталон; она тоже может быть ошибочной.']
    for index, rows in sorted(plan['runs'].items(), key=lambda x: int(x[0])):
        actual = current_runs.get(int(index), current_runs.get(str(index)))
        facts = [{'status': r['status'], 'X': r['X'], **({'memory': r['memory']} if 'memory' in r else {})} for r in rows]
        equal = []
        if actual and len(actual) == len(rows):
            for a, b in zip(actual, rows):
                try:
                    x, y = Decimal(str(a['X'])), Decimal(str(b['X']))
                    same = a['status'] == b['status'] == 'stopped' and abs(x-y) <= max(Decimal('.000002'), abs(y)*Decimal('.000002'))
                    equal.append('да' if same else 'нет')
                except (ValueError, ArithmeticError): equal.append('неизвестно')
        lines.append(f'План {int(index):02X}: '+json.dumps(facts, ensure_ascii=False, separators=(',', ':'))+
            ('; X совпал с текущим: '+','.join(equal) if equal else ''))
    return '\n'.join(lines)+'\n'


def request(s, plan=None): return render(snapshot(s), plan)


def bounded_render(tokenizer, state, plan=None):
    from ac_protocol import prompt_ids
    text = render(state, plan)
    # Drop the optional hypothesis whole, retaining every supplied case/code/fact.
    if plan is not None and len(prompt_ids(tokenizer, text)) >= 900:
        text = render(state, {'error': 'пропущена целиком из-за лимита контекста'})
        if len(prompt_ids(tokenizer, text)) >= 1016: text = render(state)
    return text


def render(state, plan=None):
    view = state['view']; runs = state['runs']; bank = input_bank(view)
    missing = [f'{i:02X}' for i in range(len(bank)) if i not in runs and str(i) not in runs]
    lines = [f'МК-61: {view["angle"]}; 105 ячеек. HEX+макросы FF01kk=константа kk.',
        'Действия: WRITE полный HEX; RUN номер случая HEX; TRACE; DONE; UNSURE.',
        'Константы: '+pool_text(state['pool']), 'Задача: '+view['task'],
        f'Осталось действий: {state["remaining"]}. Версия {state["revision"]}. Не запускались: '+(','.join(missing) if missing else 'нет')]
    for i, inputs in enumerate(bank): lines.append(f'Вход {i:02X}: '+json.dumps(inputs, ensure_ascii=False, separators=(',', ':')))
    for i, rows in sorted(runs.items(), key=lambda x: int(x[0])):
        lines.append(f'Факт {int(i):02X}: '+json.dumps(rows, ensure_ascii=False, separators=(',', ':')))
    lines.append('Текущий HEX: '+bytes_text(state['body']))
    obs = state.get('observation')
    if obs and not obs.startswith('{'): lines.append('Эмулятор: '+obs)
    lines.append(hypothesis_text(plan, runs).strip())
    lines.append('stopped означает останов, а не верность. Проверь соответствие условию. После исправления выполни проверки; правильный код заверши DONE.\nАссистент: <')
    return '\n'.join(x for x in lines if x)
