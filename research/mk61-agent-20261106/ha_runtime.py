"""External working state and oracle-free MK-61 execution observations."""
import ctypes as C
import hashlib
import json

from ha_protocol import assemble,constants,parse_call,prompt
from full_isa_vm import FullVM


def short_number(raw):
    return raw.strip().replace('  ',' ')


class Session:
    def __init__(self,task,arm,body=None,vm=None):
        self.task=task;self.arm=arm;self.pool=task.get('constants')or constants(task['task'])
        self.body=body;self.vm=vm or FullVM();self.case=0;self.observation=None;self.last_trace=None;self.history=[];self.finished=False

    def request(self,notes=''):
        return prompt(self.task,self.arm,current=self.body,observation=self.observation,case=self.case,notes=notes)

    def run(self,index):
        # Only the supplied public inputs are executable through the tool.
        # Hidden fixtures and all expected states are excluded from responses.
        cases=self.task['public_tests']
        if not 0<=index<len(cases):raise ValueError('CASE_UNAVAILABLE')
        if self.body is None:raise ValueError('NO_PROGRAM')
        code=assemble(self.body,self.pool,self.arm);context=None;reports=[];traces=[];previous={}
        for segment in cases[index]['segments']:
            inputs=segment['inputs'];actual,context=self.vm.execute(code,inputs,angle=self.task['angle'],context=context,
              max_commands=self.task.get('max_commands',128),max_frames=self.task.get('max_frames',1024))
            from decimal import Decimal
            before={r:inputs.get(r,previous.get(r,'0'))for r in actual['raw']if r.startswith('R')}
            changes={r:actual['raw'][r]for r in before if actual['numeric'][r]is None or Decimal(actual['numeric'][r])!=Decimal(str(before[r]))}
            entry={'status':actual['status'],'IP':actual['pc'],'X':short_number(actual['raw']['X']),'Y':short_number(actual['raw']['Y'])}
            if changes:entry['memory']=changes
            reports.append(entry)
            previous.update({r:actual['numeric'][r]or'0'for r in before})
            events=[]
            for i,item in enumerate(actual['trace'][:12]):
                out=C.create_string_buffer(64);self.vm.lib.mk_trace_x(i,out)
                events.append({'pc':item['pc'],'op':f'{item["opcode"]:02X}','X':short_number(out.value.decode('ascii'))})
            traces.append(events)
        self.case=index;self.last_trace=traces
        # Inputs are facts supplied to the emulator, never reference outputs.
        relevant=set(__import__('re').findall(r'\bR[0-9A-E]\b|\bX\b|\bY\b',self.task['task']))
        shown={k:v for k,v in cases[index]['segments'][0]['inputs'].items()if k in relevant}
        self.observation=json.dumps({'case':f'{index:02X}','inputs':shown,'actual':reports,'cases':len(cases)},ensure_ascii=False,separators=(',',':'))
        return self.observation

    def trace(self):
        if self.last_trace is None:raise ValueError('RUN_FIRST')
        # Only actual executed instructions and actual intermediate X values.
        self.observation='TRACE case='+f'{self.case:02X}'+' events='+ ' | '.join(
          ';'.join(f'{e["pc"]:02X}/{e["op"]}/{e["X"]}'for e in segment)for segment in self.last_trace)
        return self.observation

    def apply(self,reply):
        try:
            kind,value=parse_call(reply,self.body)
            if kind in ['write','patch']:
                assemble(value,self.pool,self.arm);self.body=value;self.run(self.case)
            elif kind=='run':self.run(value)
            elif kind=='trace':self.trace()
            elif kind=='done':self.finished=True;self.observation='DONE'
            self.history.append({'kind':kind,'reply':reply,'observation':self.observation})
            return kind
        except (ValueError,ArithmeticError,RuntimeError)as error:
            self.observation='ERROR '+str(error)
            self.history.append({'kind':'error','reply':reply,'observation':self.observation})
            return 'error'

    def snapshot(self):
        return {'task_id':self.task['id'],'arm':self.arm,'body':self.body,'case':self.case,'observation':self.observation,
          'last_trace':self.last_trace,'finished':self.finished,'history':self.history,'contains_reference_answers':False}

