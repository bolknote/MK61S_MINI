"""Revision-aware actual observations; DONE gating never inspects an oracle."""
import json
import re

from ha_protocol import prompt as old_prompt,constants,parse_call,assemble
from ha_runtime import Session as OldSession
from emulator import read_decimal

GUIDE=('После правки запусти все открытые случаи. stopped не доказывает верность: сравни X с задачей. '
       'Исправь неверный код; если все результаты верны, вызови DONE.')


def number(text):
    try:return read_decimal(text.encode('ascii'))
    except (ValueError,ArithmeticError,UnicodeEncodeError):return text


def input_bank(task):
    relevant=set(re.findall(r'\bR[0-9A-E]\b|\bX\b|\bY\b',task['task']))
    relevant.add('X')
    return [{k:v for k,v in case['segments'][0]['inputs'].items()if k in relevant}
            for case in task.get('public_tests',[])]


def prompt(task,arm='asm',*,current=None,observation=None,case=0,notes='',revision=0,runs=None):
    if current is None:
        return old_prompt(task,arm,notes=notes)
    bank=input_bank(task)
    lines=[GUIDE]
    if bank:lines.append('Открытые входы: '+'; '.join(f'{i:02X}='+json.dumps(v,ensure_ascii=False,separators=(',',':'))for i,v in enumerate(bank)))
    if current is not None:
        runs=runs or{}
        missing=[f'{i:02X}'for i in range(len(bank))if i not in runs]
        lines.append(f'Версия кода {revision}; текущий случай {case:02X}; не запускались: '+(','.join(missing)if missing else'нет'))
        for index,record in sorted(runs.items()):
            # Actual emulator output only; task expected/hidden fields are never accessed.
            lines.append(f'Факт {index:02X}: '+json.dumps(record,ensure_ascii=False,separators=(',',':')))
    if notes:lines.append(notes)
    # JSON run output is already represented in the cumulative facts above.
    # Keep traces and errors as the latest observation, without duplicating runs.
    latest=None if observation and observation.startswith('{')else observation
    return old_prompt(task,arm,current=current,observation=latest,case=case,notes='\n'.join(lines))


class Session(OldSession):
    def __init__(self,*args,gate=True,**kwargs):
        super().__init__(*args,**kwargs);self.revision=0;self.runs={};self.gate=gate;self.done_attempts=0;self.done_rejections=0

    def request(self,notes=''):
        return prompt(self.task,self.arm,current=self.body,observation=self.observation,case=self.case,
                      notes=notes,revision=self.revision,runs=self.runs)

    def run(self,index):
        observation=super().run(index)
        data=json.loads(observation)
        for row in data['actual']:
            for key in ['X','Y']:row[key]=number(row[key])
            if 'memory'in row:row['memory']={r:number(v)for r,v in row['memory'].items()}
        self.runs[index]=data['actual'];self.observation=json.dumps(data,ensure_ascii=False,separators=(',',':'))
        return self.observation

    def trace(self):
        if self.last_trace is None:raise ValueError('RUN_FIRST')
        self.observation='TRACE case='+f'{self.case:02X}'+' events='+ ' | '.join(
          ';'.join(f'{e["pc"]:02X}/{e["op"]}/{number(e["X"])}'for e in segment)for segment in self.last_trace)
        return self.observation

    def eligibility(self):
        missing=[i for i in range(len(self.task['public_tests']))if i not in self.runs]
        failed=[i for i,rows in self.runs.items()if any(r['status']!='stopped'for r in rows)]
        return not missing and not failed,missing,failed

    def apply(self,reply):
        try:
            kind,value=parse_call(reply,self.body)
            if kind=='done':
                self.done_attempts+=1;eligible,missing,failed=self.eligibility()
                if self.gate and not eligible:
                    self.done_rejections+=1
                    self.observation='DONE_REJECTED: не запускались '+','.join(f'{i:02X}'for i in missing)+'; ошибки исполнения '+','.join(f'{i:02X}'for i in failed)
                    self.history.append({'kind':'done_rejected','reply':reply,'observation':self.observation,
                                         'revision':self.revision,'missing_cases':missing,'runtime_failed_cases':failed})
                    return 'done_rejected'
                self.finished=True;self.observation='DONE'
            elif kind in ['write','patch']:
                assemble(value,self.pool,self.arm)
                self.revision+=1;self.runs.clear();self.body=value;self.run(self.case)
            elif kind=='run':self.run(value)
            elif kind=='trace':self.trace()
            self.history.append({'kind':kind,'reply':reply,'observation':self.observation,'revision':self.revision})
            return kind
        except (ValueError,ArithmeticError,RuntimeError)as error:
            self.observation='ERROR '+str(error)
            self.history.append({'kind':'error','reply':reply,'observation':self.observation,'revision':self.revision})
            return 'error'
