"""Typed recovery, visible hypothesis, and speculative code with rollback.

No hidden target is consulted. A revised hypothesis remains a hypothesis.
"""
import copy
from az_runtime import Session as Parent
from ay_runtime import render as old_render, snapshot as old_snapshot, goal_state, view
from ar_spec import spec_text
from ay_codec import decode

SPEC_DIAG = [4, 255, 255, 0, 0]


def render(state, arm='spec'):
    text = old_render(state, arm)
    if state.get('replan'):
        return text.replace('Ассистент: <', 'Повторно разбери только русское условие. Выдай SPEC; программа остаётся прежней.\nАссистент: <')
    if 'declared_spec' in state:
        note = 'Текущая гипотеза: ' + spec_text(state['declared_spec']) + '.\n'
        note += 'DIAG 04 FF FF 00 00 означает ошибку гипотезы; затем повторный разбор условия без изменения программы.\n'
        text = text.replace('Ассистент: <', note + 'Ассистент: <')
    return text


def snapshot(session):
    state = old_snapshot(session)
    state['declared_spec'] = copy.deepcopy(session.declared_spec)
    return state


class Session(Parent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pending_runs = []
        self.pending_replan = False
        self.replan_attempted = False
        self.replan_count = 0
        self.initial_spec = copy.deepcopy(self.declared_spec)
        self.saved_code = None
        self.rollback_performed = False
        self.candidate_at_exit = None

    def request(self):
        return render(snapshot(self), 'spec')

    def replan_state(self):
        return {'view': copy.deepcopy(self.task), 'pool': list(self.pool), 'body': None,
                'runs': {}, 'case': 0, 'revision': 0, 'observation': None, 'diagnosis': None,
                'remaining': 12 - len(self.history), 'replan': True}

    def replan_request(self):
        return render(self.replan_state(), 'spec')

    def apply_replan(self, body):
        # The program is deliberately untouched. Re-interpretation receives no code,
        # no hidden reference, and no numerical target from the task oracle.
        self.declared_spec = decode(body, self.pool, self.task['angle'])
        self.replan_count += 1
        self.gate_cache = None
        self.diagnosis = None
        self.observation = 'SPEC_REVISED. Это новая гипотеза условия; проверь программу.'
        self.history.append({'kind': 'replan', 'revision': self.revision, 'body': list(body),
                             'observation': self.observation})

    def apply_action(self, action, body):
        if action == 'write' and self.saved_code is None:
            self.saved_code = {k: copy.deepcopy(getattr(self, k)) for k in ['body', 'runs', 'revision', 'case', 'diagnosis']}
        result = super().apply_action(action, body)
        if action == 'done':
            self.history[-1]['evaluated_body'] = list(self.body)
        if action == 'diag' and list(body) == SPEC_DIAG and not self.replan_attempted:
            self.pending_replan = True
        if result == 'done_rejected':
            check = self.gate_checks[-1]
            if check['reason'] == 'PUBLIC_RUNS':
                self.pending_runs = list(check['missing'])
            if check['reason'] == 'SPEC_DOMAIN' and not self.replan_attempted:
                self.pending_replan = True
        return result

    def finalize(self):
        self.candidate_at_exit = list(self.body)
        if not self.finished and self.saved_code is not None:
            for k, value in self.saved_code.items():
                setattr(self, k, copy.deepcopy(value))
            self.gate_cache = None
            self.rollback_performed = True
