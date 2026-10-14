#!/usr/bin/env python3
"""Exact local ROM suffix classifies all 15 physical M1 source positions.

This is exhaustive over ring positions, NOT a key-sequence search or a
global impossibility theorem. Premise: D6 returns through A7, then E5 sees
only the real marker and false V. Native entry itself is not proved here.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);outcome=p.check()
    assert outcome==unsat,(label,p.model() if outcome==sat else outcome)
    p.pop()

for index in range(15):
    start=(index+7)%15
    seq=[0xD6,0xA7]
    while (start+len(seq))%15 not in (0,8):seq.append(0xE5)
    marker=(start+len(seq))%15
    seq.extend([0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9])
    pages=[State('source_window_%d_page_%d'%(index,i)).m for i in range(len(seq)+1)]
    a=State('source_window_'+str(index));a.m=pages[0];p=base(a,0xD6)
    p.add(stack(a)[0]==0xA7,stack(a)[1]==0xAC)
    for i,ip in enumerate(seq):
        if ip==0xE5:p.add(pages[i][22]==15 if (start+i)%15 in (0,8) else pages[i][22]!=15)
    b=a;source=[pages[0][3*j] for j in range(12)];carry=source;outputs=[]
    for i,ip in enumerate(seq):
        slot=slots[(start+i)%15];label='%d: %02X(%s)'%(index,ip,slot)
        prove(p,address(b)==ip,label+' forced address')
        out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip in (0xE7,0xA8):
            outputs.append(slot)
            prove(p,And(*[out[1+3*j]==carry[j] for j in range(12)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' exactly twelve numeric writes')
            carry=[pages[i][1+3*j] for j in range(12)]
        else:prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),label+' no ring writes')
    expected=['P7','P8','P9','P10'] if index>=7 else ['X','Y','Z','T']
    assert outputs==expected
    prove(p,And(address(b)==0xAC,b.s1==0),'finite return')
    print('PASS: M1 index %X (%s) -> marker %s -> %s; %d exact connected commands.'%
          (index,slots[start],slots[marker],'/'.join(outputs),len(seq)),flush=True)

print('CLASSIFICATION: this two-marker D6/A7 suffix writes upper Ms only from ordinary indices 7..E; indices 0..6 lift the visible stack.',flush=True)
print('LIMIT: other return addresses, additional markers or different ROM paths are not excluded.',flush=True)
