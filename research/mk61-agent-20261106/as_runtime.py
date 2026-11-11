"""Familiar AQ prompt, controlled-language formal spec, compact gate feedback."""
import copy
import json
import re
from ar_runtime import Session as Base, DIAG_GUIDE
from ar_spec import expression_text, spec_text
from ar_common import MAX_TURNS
from full_isa_math import words, registers
from hf_runtime import prompt as state_prompt
from ha_protocol import bytes_text


def view_of(goal,mode):
    text=goal['task']
    if mode=='formal':
        text='Вычисли '+words(goal['spec']['X'])+'. Результат оставь в X. '
        for register in goal['spec']['writes']:text+='Тот же результат запиши в '+register+'. '
        text+='Остальные регистры памяти сохрани; после вычисления остановись.'
    return {'id':goal['id'],'task':text,'angle':goal['angle'],'constants':goal['pool'],
            'public_tests':[{'segments':[{'inputs':x}]}for x in goal['public_inputs']],
            'max_commands':128,'max_frames':1024}


def render(view,body,pool,runs,case,revision,observation,diagnosis,remaining):
    notes=(f'Осталось действий: {remaining}. '
           'Исправление: WRITE с полным HEX программы. '
           'Проверяй результат по условию; stopped означает только останов. '
           'DONE заявляет решение. Если условие неполно или решение не найдено, UNSURE. ')
    text=state_prompt(view,'asm',current=body or None,observation=observation,case=case,
                      notes=notes,revision=revision,runs=runs)
    text=text.replace('<patch>HH LL новый суффикс</patch><run/>, ','')
    text=text.replace('Позиция суффикса HH LL — два байта индекса в текущем HEX. ','')
    text=text.replace('Константы:',DIAG_GUIDE+'\nКонстанты:',1)
    if diagnosis:
        values=diagnosis['body'];index=values[1]*256+values[2]
        actual=f'{body[index]:02X}'if index<len(body or[])else'вне кода'
        note=f'Диагноз сети, версия {diagnosis["revision"]}: '+bytes_text(values)+'; гипотеза. Фактический байт по индексу: '+actual+'.\n'
        text=text.replace('Ассистент: ',note+'Ассистент: ')
    return text+'<'


def goal_prompt(view,pool):
    # Exact empty-program AQ input, the one used by current training.
    return render(view,None,pool,{},0,0,None,None,MAX_TURNS)


class Session(Base):
    def request(self):
        # No new initial spec notation; the gate keeps its declared spec outside
        # the neural context. Both models and both gates start with this text.
        return render(self.task,self.body,self.pool,self.runs,self.case,self.revision,
                      self.observation,self.diagnosis,MAX_TURNS-len(self.history))

    def apply_action(self,action,body):
        result=super().apply_action(action,body)
        if result=='done_rejected':
            check=self.gate_checks[-1]
            relevant=set(re.findall(r'\bR[0-9A-E]\b|\b[XYZT]\b',spec_text(self.declared_spec)))
            values={k:v for k,v in check.get('inputs',{}).items()if k in relevant}
            short='DONE_REJECTED. '
            if check['reason']=='PUBLIC_RUNS':
                short+='Не запускались: '+','.join(f'{x:02X}'for x in check['missing'])+'.'
            elif check['reason']=='COUNTEREXAMPLE':
                # A mathematical counterexample to the declared hypothesis,
                # never an expected value derived from the hidden user oracle.
                short+='По гипотезе '+spec_text(self.declared_spec)+': '
                short+=','.join(k+'='+str(v)for k,v in values.items())
                short+='; '+check['name']+'='+str(check['actual'])+', ожидается '+format(check['expected'],'.8g')+'.'
            else:short+=check['reason']+'.'
            self.observation=short
            self.history[-1]['observation']=short
        return result
