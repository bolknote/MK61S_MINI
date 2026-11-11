"""One shared, oracle-free tool state for small and large actors."""
import copy
import json
from ar_common import MAX_TURNS
from ar_spec import spec_text, verify
from hf_runtime import Session as Parent, prompt as state_prompt
from ha_protocol import bytes_text, pool_text, assemble

DIAG_GUIDE = ('DIAG: <diag>TT HH LL AA BB</diag>. TT: 00=верно, 01=операция, 02=аргумент, 03=порядок. '
              'HH LL — первый индекс различия в текущем HEX; AA — текущий байт; BB — нужный байт. '
              'Для верного кода: 00 FF FF 00 00. Диагноз — гипотеза; исправляй WRITE и проверяй RUN.')


def view_of(goal, mode):
    text = goal['task'] if mode == 'natural' else (
        'Вычисли по точной спецификации: '+spec_text(goal['spec'])+'. После вычисления остановись.')
    return {'id': goal['id'], 'task': text, 'angle': goal['angle'], 'constants': goal['pool'],
            'public_tests': [{'segments':[{'inputs':x}]} for x in goal['public_inputs']],
            'max_commands':128, 'max_frames':1024}


def goal_prompt(view, pool):
    return (f'МК-61: {view["angle"]}; 105 ячеек. HEX+макросы FF01kk=константа kk.\n'
            'Константы: '+pool_text(pool)+'\nЗадача: '+view['task']+'\n'
            'Составь гипотезу решения: полный HEX программы, результат в X. Это план, ещё не проверенный по условию.\nАссистент: <')


class Session(Parent):
    def __init__(self, view, body, vm, declared_spec, checker_inputs, gate):
        # No gold task/spec/reference is passed here in natural mode.
        super().__init__(view,'asm',body=copy.deepcopy(body),vm=vm,gate=False)
        self.declared_spec = copy.deepcopy(declared_spec)
        self.checker_inputs = checker_inputs
        self.mechanical = gate
        self.abstained = False
        self.diagnosis = None
        self.gate_checks = []
        self.gate_cache = None
        for index in range(len(view['public_tests'])):
            self.run(index)
        self.case=0;self.observation=None;self.history=[]

    def request(self):
        notes=(f'Осталось действий: {MAX_TURNS-len(self.history)}. '
               'Исправление: WRITE с полным HEX программы. '
               'Проверяй результат по условию; stopped означает только останов. '
               'DONE заявляет решение. Если условие неполно или решение не найдено, UNSURE. ')
        # Identical facts for raw/mechanical arms, including the declared spec.
        notes += '\nФормальная гипотеза: '+spec_text(self.declared_spec)+'. '
        notes += 'Совпадение кода с гипотезой само по себе не подтверждает понимание запроса.\n'
        if self.diagnosis:
            values=self.diagnosis['body'];at=values[1]*256+values[2]
            actual=f'{self.body[at]:02X}'if at<len(self.body or[])else'вне кода'
            notes+=f'Диагноз сети, версия {self.diagnosis["revision"]}: '+bytes_text(values)+'; гипотеза. Фактический байт по индексу: '+actual+'.\n'
        text=state_prompt(self.task,'asm',current=self.body,observation=self.observation,
                          case=self.case,notes=notes,revision=self.revision,runs=self.runs)
        text=text.replace('Константы:',DIAG_GUIDE+'\nКонстанты:',1)
        text=text.replace('<patch>HH LL новый суффикс</patch><run/>, ','')
        text=text.replace('Позиция суффикса HH LL — два байта индекса в текущем HEX. ','')
        return text+'<'

    def apply_action(self, action, body):
        if action not in ['write','run','trace','done','unsure','diag']:
            raise ValueError('ACTION')
        if action=='unsure':
            self.abstained=True;self.observation='UNSURE'
        elif action=='diag':
            if len(body)!=5:raise ValueError('DIAG_LENGTH')
            self.diagnosis={'revision':self.revision,'body':list(body)}
            self.observation='DIAG_HYPOTHESIS'
        elif action=='done':
            if self.mechanical:
                eligible,missing,failed=self.eligibility()
                if not eligible:
                    result={'status':'FAIL','reason':'PUBLIC_RUNS','missing':missing,'failed':failed}
                else:
                    if self.gate_cache is None:
                        self.gate_cache=verify(self.vm,self.body,self.pool,self.declared_spec,self.checker_inputs)
                    result=self.gate_cache
                self.gate_checks.append({'revision':self.revision,**copy.deepcopy(result)})
                if result['status']!='TESTED':
                    self.observation='DONE_REJECTED '+json.dumps(result,ensure_ascii=False,separators=(',',':'))
                    self.history.append({'kind':'done_rejected','revision':self.revision,'body':list(body),'observation':self.observation})
                    return 'done_rejected'
            self.finished=True;self.observation='DONE'
        elif action=='write':
            assemble(body,self.pool,'asm')
            self.body=list(body);self.revision+=1;self.runs.clear();self.gate_cache=None;self.diagnosis=None
            self.run(self.case)
        elif action=='run':
            if len(body)!=1:raise ValueError('RUN_LENGTH')
            self.run(body[0])
        else:self.trace()
        self.history.append({'kind':action,'revision':self.revision,'body':list(body),'observation':self.observation})
        return action
