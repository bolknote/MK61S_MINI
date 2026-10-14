#!/usr/bin/env python3
"""Three conditional ROM entries for non-shifting marker cloning.

Native source preparation and formatter return are separate obligations.
The connected suffix below ends on entry to A3, not after the formatter.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()

for control in ['V','Q','control']:
    start=slots.index(control)
    seq=[0x9C,0x9E,0x9F,0xA0]
    current=lambda:slots[(start+len(seq))%15]
    # Real marker, the earlier U marker, and optionally an already cloned W.
    while current() not in ['marker','U','W']:seq.append(0xE5)
    seq.extend([0xE5,0xE6,0xED,0xEE,0xA1])
    while current() not in ['marker','U','W']:seq.append(0xE5)
    seq.extend([0xE5,0xE6,0xE9])
    target=slots[(start+len(seq)-1)%15]
    while current() not in ['marker','X','U','W']:seq.append(0xA2)
    seq.append(0xA2)
    names=[slots[(start+i)%15] for i in range(len(seq)+1)]
    pages={n:State('clone_'+control+'_'+n).m for n in slots}
    a=State('clone_'+control);a.m=pages[control];p=base(a,0x9C)
    accepted=pages[control]
    p.add(a.r[30]==4,a.r[33]==1,
          If(accepted[31]==15,UGE(accepted[34],1),UGE(accepted[34],7)))
    marker='0000F0000000'
    for j,digit in enumerate(reversed(marker)):
        p.add(pages['X'][1+3*j]==int(digit,16))
    for n,ip in zip(names,seq):
        if ip in [0xE5,0xA2]:
            p.add(pages[n][22]==15 if n in ['marker','X','U','W'] else pages[n][22]!=15)
    b=a;source=None
    for i,ip in enumerate(seq):
        label='%s: %02X(%s)'%(control,ip,names[i])
        prove(p,address(b)==ip,label+' forced address')
        if ip==0xEE:source=names[i]
        out=[];b=ex(b,ip,*keys(label+str(i)),serial_inputs=pages[names[i+1]],emitted_outputs=out)
        if ip==0xE9:
            prove(p,And(*[out[1+3*j]==pages[source][1+3*j] for j in range(12)],
                        *[out[j]==pages[target][j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' exactly 12 source tetras; other lanes and service held')
        else:
            prove(p,And(*[out[j]==pages[names[i]][j] for j in range(42)]),label+' ring held')
    prove(p,address(b)==0xA3,control+' finite request return')
    assert (source,target,names[-1])==(('Q','X1','Y') if control=='control' else ('X','W','control'))
    print('PASS: accepted %s -> EE(%s) -> E9(%s) -> A3(%s), %d connected commands; upper Ms untouched.'%
          (control,source,target,names[-1],len(seq)),flush=True)
print('LIMIT: conditional suffix only; whole keyboard preparation, all phases, secondary-chip actions and later formatter require native tests.',flush=True)
