"""Actual execution only. DIAG records a hypothesis, never consults a gold program."""
from hf_runtime import Session as Parent, prompt as parent_prompt
from aa_common import MAX_TURNS
from aa_protocol import as_xml


def initial_prompt(task):
    # The old first-shot instruction stays identical except for an action prefix.
    return parent_prompt(task) + '<'


class Session(Parent):
    def __init__(self, *args, max_turns=MAX_TURNS, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_turns = max_turns
        self.abstained = False
        self.diagnosis = None

    def request(self, notes=''):
        if self.body is None: return initial_prompt(self.task)
        remaining = self.max_turns - len(self.history)
        note = f'Осталось действий: {remaining}. Если задача не решена, не объявляй DONE. При нехватке данных используй UNSURE.'
        if self.diagnosis is not None:
            note += ' Твоя гипотеза DIAG: ' + ' '.join(f'{b:02X}' for b in self.diagnosis) + '.'
        return super().request(notes=(note+' '+notes).strip()) + '<'

    def apply_action(self, action, body):
        if action == 'unsure':
            self.abstained = True
            self.history.append({'kind': action, 'observation': 'UNSURE'})
            return action
        if action == 'diag':
            try:
                if len(body) != 5: raise ValueError('DIAG_LENGTH')
                at = body[3]*256 + body[4]
                if self.body is None or at >= len(self.body) or self.body[at] != body[2]:
                    raise ValueError('DIAG_POSITION_OR_ACTUAL_BYTE')
                self.diagnosis = list(body)
                self.observation = 'DIAG_HYPOTHESIS: не является проверкой правильности; выполни правку и запуски.'
                kind = 'diag'
            except ValueError as error:
                self.observation = 'ERROR ' + str(error)
                kind = 'error'
            self.history.append({'kind': kind, 'body': body, 'observation': self.observation})
            return kind
        kind = super().apply(as_xml(action, body))
        if kind in ['write', 'patch']: self.diagnosis = None
        return kind
