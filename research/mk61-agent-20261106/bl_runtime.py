"""Compact protocol plus explicit remaining review and code-free hypothesis review."""
import copy
import hashlib
from bj_runtime import Session as Parent, render as previous_render, snapshot as previous_snapshot
from ar_spec import spec_text
from bl_prompt import fit


def decorate(text, question, attempted=False, prior_spec_marker=False, prior_spec=None):
    question = question.strip(); at = text.index('Задача: ') + len('Задача: ')
    assert text[at:at + len(question)] == question
    marker = '\x00QUESTION_' + hashlib.sha256(question.encode()).hexdigest() + '\x00'
    assert marker not in text
    text = text[:at] + marker + text[at + len(question):]
    if attempted and not prior_spec_marker:
        text = text.replace('DIAG 04 FF FF 00 00 означает ошибку гипотезы; затем повторный разбор условия без изменения программы.',
                            'Повторный разбор SPEC уже выполнен. Если гипотеза всё ещё неверна, UNSURE.')
    if prior_spec_marker:
        note = 'Первая гипотеза: ' + spec_text(prior_spec) + '. Сохрани её, если она соответствует условию; иначе исправь. Код не показан.\n'
        text = text.replace('Повторно разбери только русское условие.', note + 'Повторно разбери только русское условие.', 1)
    elif 'Текущая гипотеза:' in text:
        text = text.replace('Ассистент: <', 'Разборов SPEC осталось: ' + ('0' if attempted else '1') + '.\nАссистент: <')
    return text.replace(marker, question)


def render(state, tokenizer):
    text = previous_render(state, 'spec')
    text = decorate(text, state['view']['task'], state.get('replan_attempted', False),
                    state.get('replan', False), state.get('prior_spec'))
    return fit(text, state['view']['task'], tokenizer)


def direct_prompt(row, tokenizer):
    text = decorate(row['raw_prompt'], row['question'], row['replan_attempted'])
    return fit(text, row['question'], tokenizer)


class Session(Parent):
    tokenizer = None

    def request(self):
        state = previous_snapshot(self); state['replan_attempted'] = self.replan_attempted
        prompt, self.last_budget = render(state, self.tokenizer)
        return prompt

    def replan_state(self):
        state = super().replan_state(); state['prior_spec'] = copy.deepcopy(self.declared_spec)
        state['replan_attempted'] = True
        return state

    def replan_request(self):
        prompt, self.last_budget = render(self.replan_state(), self.tokenizer)
        return prompt
