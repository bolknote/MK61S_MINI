"""Remove redundant protocol text; retain question, code, facts and hypothesis."""
import hashlib
import json
import re
from ar_runtime import DIAG_GUIDE
from hf_runtime import GUIDE
from aq_protocol import prompt_ids
from bj_runtime import render as long_render

CONTEXT = 1024
RESERVE = 160  # 31-node SPEC <=48 bytes <=143 ASCII tokens, plus header and END.
LIMIT = CONTEXT - RESERVE


def compact(text, question, level=1):
    question = question.strip()
    start = text.index('Задача: ') + len('Задача: ')
    assert text[start:start + len(question)] == question
    marker = '\x00MK61_QUESTION_' + hashlib.sha256(question.encode()).hexdigest() + '\x00'
    assert marker not in text
    text = text[:start] + marker + text[start + len(question):]
    text = text.replace(DIAG_GUIDE + '\n', '', 1)
    text = text.replace(GUIDE + '\n', '', 1)
    text = text.replace('R0–RE, стек X/Y/Z/T/X1. HEX+макросы FF00=байт FF, FF01kk=константа kk, FF02ll=метка ll, FF03ll=адрес метки ll.', 'FF01kk=константа kk.', 1)
    text = text.replace(' Эмулятор сообщает фактическое состояние.', '', 1)
    text = text.replace('Текущий HEX (индекс в начале каждой строки):', 'Текущий HEX:')
    # The same current hypothesis appears again in COUNTEREXAMPLE feedback.
    match = re.search(r'^Текущая гипотеза: (.*)\.$', text, re.M)
    if match:
        text = text.replace('По гипотезе ' + match[1] + ': ', 'По гипотезе: ', 1)
    if level >= 2:
        # Exact identical facts retain all case IDs and every numeric field.
        lines = text.splitlines(); facts = {}; order = []
        for line in lines:
            match = re.fullmatch(r'Факт ([0-9A-F]{2}): (.*)', line)
            if match:
                if match[2] not in facts:
                    facts[match[2]] = []; order.append(match[2])
                facts[match[2]].append(match[1])
        seen = set(); changed = []
        for line in lines:
            match = re.fullmatch(r'Факт ([0-9A-F]{2}): (.*)', line)
            if match:
                if match[2] in seen:
                    continue
                seen.add(match[2]); line = 'Факт ' + ','.join(facts[match[2]]) + ': ' + match[2]
            changed.append(line)
        text = '\n'.join(changed)
        text = text.replace('Исправление: WRITE с компактной спецификацией SPEC. ', '', 1)
        text = text.replace('DIAG 04 FF FF 00 00 означает ошибку гипотезы; затем повторный разбор условия без изменения программы.',
                            'DIAG 04 FF FF 00 00: ошибка гипотезы; повторный разбор без изменения программы.', 1)
    if level >= 3:
        # Only protocol prose is abbreviated. No task or observed state is cut.
        text = text.replace('Вызовы: <write>SPEC</write><run/>, <run>номер теста HEX</run>, <trace/>, <done/>.',
                            'Вызовы: WRITE SPEC; RUN номер HEX; TRACE; DONE; UNSURE.')
        text = text.replace('Проверяй результат по условию; stopped означает только останов. DONE заявляет решение. Если условие неполно или решение не найдено, UNSURE.',
                            'stopped — только останов. DONE — решение условия; иначе UNSURE.')
    return text.replace(marker, question)


def fit(text, question, tokenizer):
    before = len(prompt_ids(tokenizer, text))
    if before <= LIMIT:
        return text, {'level': 0, 'before': before, 'after': before, 'reserve': RESERVE, 'fits': True}
    for level in [1, 2, 3]:
        result = compact(text, question, level)
        after = len(prompt_ids(tokenizer, result))
        if after <= LIMIT:
            return result, {'level': level, 'before': before, 'after': after, 'reserve': RESERVE, 'fits': True}
    return result, {'level': 3, 'before': before, 'after': after, 'reserve': RESERVE, 'fits': False}


def render(state, tokenizer):
    return fit(long_render(state, 'spec'), state['view']['task'], tokenizer)
