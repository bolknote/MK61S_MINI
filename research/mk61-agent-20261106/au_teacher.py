"""Reference-assisted teacher diagnostic, separate from the matched input runs.

The ISA reference is task independent and available only to this teacher arm.
This is a protocol diagnostic, not a fair unassisted size comparison.
"""
import argparse
import hashlib
import json
import threading
import time
from pathlib import Path

import ar_run
import as_run
from ar_common import HERE, REPO, MODEL, read, write, sha
from ar_common import ROOT as FIRST
from ar_spec import verify
from full_isa_vm import FullVM

ROOT=REPO/'.build/mk61-agent-20261106/spec-diagnostic-reference-v1'
REFERENCE=('Справочник команд и интерфейса МК-61. Программа занимает НЕ БОЛЕЕ 105 байтов: '
 'НЕ дополняй её нулями или NOP до 105. Каждый байт — ровно две HEX-цифры, байты разделены пробелами. '
 '50=С/П (останов), 54=NOP; 60..6E=чтение R0..RE в X с подъёмом стека; '
 '40..4E=запись X в R0..RE без изменения X. 0E=В↑, 0D=очистка X, 00..09=цифры, 0A=точка, '
 '0B=смена знака. Константа kk из таблицы: три отдельных байта FF 01 kk. '
 'Не подставляй значение регистра константой. '
 'Унарные команды в X: 15=10^X,16=exp,17=log10,18=ln,19=asin,1A=acos,1B=atan,1C=sin,1D=cos,1E=tan, '
 '20=pi,21=sqrt,22=square,23=1/X,31=abs,32=sign,34=int (к нулю),35=frac (исходный знак). '
 'Бинарные команды: 10=Y+X,11=Y-X,12=Y*X,13=Y/X; результат в X, стек опускается. '
 'Для a^b сначала получи b, затем a, затем 24 14 0D 10; эта последовательность нормализует стек. '
 'Режим углов устанавливает harness. '
 'WRITE — заменить программу полным HEX и автоматически запустить текущий открытый случай. '
 'RUN — запустить уже загруженную программу на открытом тесте; body содержит РОВНО ОДИН байт номера теста, НЕ код программы. '
 'TRACE, DONE, UNSURE имеют пустой body. DIAG имеет ровно пять байтов. '
 'Не выдавай RUN с текстом программы. Возвращай ровно одно действие.\n\n')


def check_frozen():
    frozen=read(ROOT/'frozen.json')
    for name,digest in frozen['sources'].items():assert sha(HERE/name)==digest,name
    for name,digest in frozen['data'].items():assert sha(ROOT/name)==digest,name
    assert sha(MODEL/'model.mkqb')==frozen['small_packet_sha256']


class ReferenceTeacher(ar_run.Teacher):
    def __init__(self):
        super().__init__();self.key_locks={};self.guard=threading.Lock()

    def one(self,prompt,forced):
        full=REFERENCE+prompt
        with self.guard:lock=self.key_locks.setdefault((full,forced),threading.Lock())
        with lock:return super().one(full,forced)


def prepare():
    assert not(ROOT/'frozen.json').exists()
    write(ROOT/'goals.json',read(FIRST/'goals.json'))
    policy=read(REPO/'.build/mk61-agent-20261106/spec-diagnostic-native-v1/policy.json')
    policy.update({'arm':'Qwen with explicit task-independent ISA reference',
                   'fair_unassisted_size_comparison':False,
                   'reason':'without a reference the teacher returns invalid padded programs and cannot supply its own spec',
                   'same_tools_and_turn_budget':True,'thinking':False,'reference_sha256':hashlib.sha256(REFERENCE.encode()).hexdigest()})
    write(ROOT/'policy.json',policy);(ROOT/'reference.txt').write_text(REFERENCE)
    sources={p.name:sha(p)for p in HERE.glob('*.py')if not p.name.endswith(('_report.py','_remote.py'))}
    write(ROOT/'frozen.json',{'unix':time.time(),'sources':sources,
                             'data':{n:sha(ROOT/n)for n in ['policy.json','goals.json','reference.txt']},
                             'small_packet_sha256':sha(MODEL/'model.mkqb'),
                             'new_final_test':False,'training_updates':0})
    print(json.dumps({'reference_frozen':True,'new_final_test':False}))


def preflight():
    check_frozen();ar_run.ROOT=ROOT
    actor=ReferenceTeacher();vm=FullVM();pool=['0','1','-1']
    examples=[('square_R7','Вычисли квадрат R7. Результат оставь в X. Остальную память сохрани.', ['square','R7']),
              ('subtract_R7_R8','Вычти R8 из R7. Результат оставь в X. Остальную память сохрани.', ['-','R7','R8'])]
    rows=[]
    for name,text,expr in examples:
        view={'id':name,'task':text,'angle':'RAD','constants':pool,'public_tests':[]}
        prompt=as_run.goal_prompt(view,pool);generation=actor.one(prompt,'write')
        spec={'X':expr,'writes':{},'angle':'RAD'}
        result=verify(vm,generation['body'],pool,spec,[{'R7':'2.25','R8':'-1.5'},{'R7':'-3.25','R8':'0.875'}])
        rows.append({'id':name,'generation':generation,'ROM_check':result})
    write(ROOT/'preflight.json',rows);print(json.dumps(rows,ensure_ascii=False))
    assert all(r['ROM_check']['status']=='TESTED'for r in rows),'teacher reference preflight failed'


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','preflight','run']);a=p.parse_args()
    if a.action=='prepare':prepare();return
    if a.action=='preflight':preflight();return
    assert(ROOT/'preflight.json').exists()
    ar_run.ROOT=ROOT;ar_run.check_frozen=check_frozen;ar_run.Teacher=ReferenceTeacher
    ar_run.run('teacher')


if __name__=='__main__':main()
