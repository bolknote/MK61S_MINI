"""Public tool semantics are identical to v1; only neural header handling changes."""
from aa_runtime import Session as Parent,initial_prompt


class Session(Parent):
    def apply_action(self,action,body):
        if action!='diag':return super().apply_action(action,body)
        if len(body)!=5:raise ValueError('DIAG_LENGTH')
        at=body[3]*256+body[4]
        actual=self.body[at]if self.body is not None and at<len(self.body)else None
        self.diagnosis=list(body)
        fact='адрес вне кода'if actual is None else f'фактический байт {actual:02X}'
        self.observation=f'DIAG_HYPOTHESIS: версия модели, не доказательство. По адресу {at:04X}: {fact}. Исправь код и проверь запусками.'
        self.history.append({'kind':'diag','body':body,'observation':self.observation,
                             'citation_matches_actual':actual==body[2]})
        return 'diag'
