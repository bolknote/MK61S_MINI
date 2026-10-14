#!/usr/bin/env python3
"""Primary guard: true control and V marker copy arbitrary P7 into X1.

This is a local dispatch contract, not the secondary SIGN or its formatter.
"""
import runpy
from pathlib import Path
from z3 import And,If,UGE,ZeroExt,sat,unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
seq=[0x9C,0x9E,0x9F,0xA0]+[0xE5]*4+[0xE6,0xED,0xEE,0xA1]+[0xE5]*3+[0xE6,0xE9]
names=[slots[(1+i)%15] for i in range(len(seq)+1)]
pages={n:State('v_q_guard_'+n).m for n in slots}
a=State('v_q_guard');a.m=pages['control'];p=base(a,0x9C)
p.add(a.r[30]==2,a.r[33]==3,If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
for n,ip in zip(names,seq):
    if ip==0xE5:p.add(pages[n][22]==15 if n in ('marker','V') else pages[n][22]!=15)
def prove(claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()
b=a
for i,ip in enumerate(seq):
    n=names[i];label='%02X(%s)'%(ip,n);prove(address(b)==ip,label+' forced')
    out=[];b=ex(b,ip,*keys('guard_keys_'+str(i)),serial_inputs=pages[names[i+1]],emitted_outputs=out)
    if ip==0xE9:
        prove(And(*[out[1+3*j]==pages['P7'][1+3*j] for j in range(12)],
                  *[out[j]==pages['X1'][j] for j in range(42) if j%3!=1 or j>=37]),'exact P7 to X1')
    else:prove(And(*[x==y for x,y in zip(out,pages[n])]),label+' ring held')
prove(address(b)==0xA2,'returns A2')
print('PASS 17 connected primary commands: arbitrary P7 -> X1, all other ring tetras held.',flush=True)
print('LIMIT: V placement, SIGN and late formatting are separate obligations.',flush=True)
