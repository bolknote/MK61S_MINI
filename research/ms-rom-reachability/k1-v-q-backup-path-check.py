#!/usr/bin/env python3
"""Conditional ENTER(W) and Last-X(Q/V) visible pushes, before formatting."""
import runpy
from pathlib import Path
from z3 import And,ZeroExt,sat,unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
stack=lambda a:[ZeroExt(4,a.st[36+i])|(ZeroExt(4,a.st[39+i])<<4) for i in range(3)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def check(source,last):
    tag='v_q_backup_'+source
    seq=[0xEE]+([0xF0] if last else [])+[0xE0,0xA7]
    where=lambda:slots[(slots.index(source)+len(seq))%15]
    while where()!='marker':seq.append(0xE5)
    seq += [0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
    names=[slots[(slots.index(source)+i)%15] for i in range(len(seq)+1)]
    pages={n:State(tag+'_'+n).m for n in slots}
    a=State(tag);a.m=pages[source];p=base(a,0xEE)
    p.add(a.s1==(14 if last else 13),
          *[x==v for x,v in zip(stack(a),[0xF0 if last else 0xE0,0x8E,0x9A])])
    if not last:p.add(a.r[23]==0,a.r[26]==0,a.r[29]==0)
    for n,ip in zip(names,seq):
        if ip==0xE5:p.add(pages[n][22]==15 if n=='marker' else pages[n][22]!=15)
    def prove(claim,label):
        assert p.check()==sat,('empty premises',label)
        p.push();p.add(~claim);answer=p.check()
        assert answer==unsat,(label,p.model() if answer==sat else answer)
        p.pop()
    b=a;carried=[pages[source][1+3*j] for j in range(12)];written=[]
    for i,ip in enumerate(seq):
        n=names[i];label='%02X(%s)'%(ip,n);prove(address(b)==ip,label+' forced')
        out=[];b=ex(b,ip,*keys(tag+str(i)),serial_inputs=pages[names[i+1]],emitted_outputs=out)
        if ip==0xF0:prove(b.r[26]==0,label+' clears R26 regardless of its old value')
        if ip in (0xE7,0xA8):
            prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                      *[out[j]==pages[n][j] for j in range(42) if j%3!=1 or j>=37]),label+' exact write')
            written.append(n);carried=[pages[n][1+3*j] for j in range(12)]
        else:prove(And(*[x==y for x,y in zip(out,pages[n])]),label+' ring held')
        if ip!=0xA9:prove(And(*[b.r[3*j]==carried[j] for j in range(12)]),label+' payload held')
    assert written==['X','Y','Z','T']
    prove(address(b)==0xE1,'returns to E1')
    print('PASS',source,'read and visible push:',len(seq),'connected commands; arbitrary 12-tetra payloads.',flush=True)
    if last:print('PASS LastX push is forced with arbitrary initial R23/R26/R29; entry flags cannot suppress it.',flush=True)

check('W',False)
check('Q',True)
check('V',True)
print('LIMIT: conditional read/push only. Native control selection and later P7 formatting are separate checks.',flush=True)
