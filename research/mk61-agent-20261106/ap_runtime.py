"""Identical public facts in both formats; diagnoses remain model hypotheses."""
import copy
from an_runtime import render as legacy_render
from hf_runtime import GUIDE
from ac_runtime import Session as Parent
from ap_common import MAX_TURNS, ACTIONS
from ha_protocol import bytes_text

FIXED = ('Исправление: WRITE с полным HEX программы. '
         'Проверяй результат по условию; stopped означает только останов. '
         'DONE заявляет решение. Если условие неполно или решение не найдено, UNSURE. ')
DIAG_GUIDE = ('DIAG: <diag>TT HH LL AA BB</diag>. TT: 00=верно, 01=операция, 02=аргумент, 03=порядок. '
              'HH LL — первый индекс различия в текущем HEX; AA — текущий байт; BB — нужный байт. '
              'Для верного кода: 00 FF FF 00 00. Диагноз — гипотеза; исправляй WRITE и проверяй RUN.')


def render(state, arm='full'):
    text = legacy_render(state)
    text = text.replace('Константы:', DIAG_GUIDE + '\nКонстанты:', 1)
    diagnosis = state.get('diagnosis')
    if diagnosis:
        revision = diagnosis['revision']
        values = diagnosis['body']
        index = values[1] * 256 + values[2]
        actual = state['body'][index] if index < len(state['body'] or []) else None
        fact = 'вне кода' if actual is None else f'{actual:02X}'
        note = f'Диагноз сети, версия {revision}: {bytes_text(values)}; гипотеза. Фактический байт по индексу: {fact}.\n'
        text = text.replace('Ассистент: <', note + 'Ассистент: <')
    if arm == 'short':
        text = f'Режим: {state["view"]["angle"]}.\n' + text[text.index('Константы:'):]
        text = text.replace(GUIDE + '\n', '').replace(FIXED, '')
    assert arm in ['full', 'short']
    return text


def snapshot(s):
    return {'view': s.task, 'pool': s.pool, 'body': copy.deepcopy(s.body), 'runs': copy.deepcopy(s.runs),
            'case': s.case, 'revision': s.revision, 'remaining': MAX_TURNS - (len(s.history) - s.initial_history),
            'observation': s.observation, 'diagnosis': copy.deepcopy(s.diagnosis)}


class Session(Parent):
    def __init__(self, view, pool, body, vm, arm):
        super().__init__({**view, 'constants': pool}, 'asm', body=body, vm=vm, gate=False, max_turns=MAX_TURNS)
        self.format_arm = arm
        self.diagnosis = None
        self.initial_history = 0

    def request(self, notes=''):
        return render(snapshot(self), self.format_arm)

    def apply_action(self, action, body):
        if action == 'diag':
            if len(body) != 5:
                raise ValueError('DIAG_LENGTH')
            self.diagnosis = {'revision': self.revision, 'body': list(body)}
            self.history.append({'kind': 'diag', 'body': list(body), 'revision': self.revision,
                                 'observation': 'DIAG_HYPOTHESIS'})
            return 'diag'
        assert action in ACTIONS
        if action == 'write':
            self.diagnosis = None
        return super().apply_action(action, body)


def diagnosis(body, reference, label):
    if label == 'correct':
        return [0, 255, 255, 0, 0]
    kind = {'operation': 1, 'argument': 2, 'order': 3}[label]
    at = next((i for i, (a, b) in enumerate(zip(body, reference)) if a != b), min(len(body), len(reference)))
    return [kind, at // 256, at % 256, body[at] if at < len(body) else 0, reference[at] if at < len(reference) else 0]
