"""Real public execution; no reference code or expected states are read here."""
import re
from hf_runtime import Session as Parent
from hf_runtime import prompt as original_prompt
from ac_common import MAX_TURNS,ACTIONS
from ac_protocol import as_xml


class Session(Parent):
    def __init__(self,*args,max_turns=MAX_TURNS,**kwargs):
        super().__init__(*args,**kwargs);self.max_turns=max_turns;self.abstained=False

    def request(self,notes=''):
        extra=(f'Осталось действий: {self.max_turns-(len(self.history)-getattr(self,"initial_history",0))}. '
               'Исправление: WRITE с полным HEX программы. '
               'Проверяй результат по условию; stopped означает только останов. '
               'DONE заявляет решение. Если условие неполно или решение не найдено, UNSURE. ')+notes
        text=super().request(notes=extra)
        # Remove the retired PATCH interface, keeping the existing input language.
        text=text.replace('<patch>HH LL новый суффикс</patch><run/>, ','')
        text=text.replace('Позиция суффикса HH LL — два байта индекса в текущем HEX. ','')
        return text+'<'

    def apply_action(self,action,body):
        if action not in ACTIONS:raise ValueError('Unsupported action')
        if action=='unsure':
            self.abstained=True;self.observation='UNSURE'
            self.history.append({'kind':'unsure','observation':self.observation,'revision':self.revision})
            return 'unsure'
        return super().apply(as_xml(action,body))

    def trace_seen(self):
        return any(h['kind']=='trace'and h.get('revision')==self.revision for h in self.history)
