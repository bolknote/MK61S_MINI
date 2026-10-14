#!/usr/bin/env python3
"""Exact secondary dispatch prefixes for candidate pending request bytes.

Arbitrary unrelated state, all numeric words and per-tick keyboard inputs.
Stops at the first non-forced address or memory write: not native reachability.
"""
import json
import runpy
import subprocess
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
rom=json.loads(subprocess.check_output(['node','-e',
    'console.log(JSON.stringify(require(process.argv[1])["ИК1303"]))',str(q['ROM_PATH'])],text=True))
q['execute_command'].__globals__.update(COMMANDS=rom['команды'],
    SYNCS=rom['синхропрограммы'],MICROS=rom['микрокоманды'])
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prefix(opcode):
    pages={n:State('request_%02X_%s'%(opcode,n)).m for n in slots}
    a=State('request_%02X'%opcode);a.m=pages['W'];p=base(a,0x6E)
    p.add(a.r[29]==0,pages['Q'][31]==opcode%16,pages['Q'][34]==opcode//16)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Y','W') else pages[n][22]!=15)
    assert p.check()==sat
    b=a;route=[]
    for i in range(60):
        p.push();ips=q['possible_values'](address(b),p,257);p.pop()
        if len(ips)!=1:return {'opcode':'%02X'%opcode,'route':route,'next':['%02X'%ip for ip in ips]}
        ip=ips[0];name=slots[(9+i)%15]
        route.append('%02X(%s)'%(ip,name))
        out=[];b=ex(b,ip,*keys('request_%02X_%d'%(opcode,i)),
                    serial_inputs=pages[slots[(10+i)%15]],emitted_outputs=out)
        p.push();p.add(Or(*[x!=y for x,y in zip(out,pages[name])]))
        writes=p.check()==sat;p.pop()
        if writes:return {'opcode':'%02X'%opcode,'route':route,'stopped':'possible ring write'}
        if ip==0x39:
            p.push();p.add(Or(address(b)!=0x6E,b.r[29]!=0));quiet=p.check()==unsat;p.pop()
            return {'opcode':'%02X'%opcode,'route':route,'quietReturn':quiet}
    return {'opcode':'%02X'%opcode,'route':route,'stopped':'bounded prefix'}

if __name__=='__main__':
    for opcode in (0,0x14,0x1F,*range(0x20,0x30)):
        print(json.dumps(prefix(opcode)),flush=True)
