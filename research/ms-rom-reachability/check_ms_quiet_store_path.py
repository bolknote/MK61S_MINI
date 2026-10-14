#!/usr/bin/env python3
"""Connected Q-accepted direct store 4A: physical X -> ordinary P4.

Entry source selection and the later formatter are separate native-test
obligations. The stored twelve-tetra source here is otherwise arbitrary.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
pages={n:State('quiet_store_'+n).m for n in slots}
a=State('quiet_store');a.m=pages['Q'];p=base(a,0x9C)
p.add(a.r[30]==10,a.r[33]==4,pages['Q'][34]==1,pages['Q'][31]==15)
seq=[0x9C,0x9E,0x9F,0xAA,0xE5,0xE5,0xE6,0xED,0xEE,0xAB,0xAD,0xA4,
     1,1,1]+[2]*11+[3,4,0xBA,0xCB,0xDD,0xD4]
for i,ip in enumerate(seq):
    name=slots[(10+i)%15]
    if ip in (1,0xE5):p.add(pages[name][22]==15 if name in ('marker','W') else pages[name][22]!=15)

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop();print('PASS:',label,flush=True)

b=a;source=[pages['X'][1+3*j] for j in range(12)]
for i,ip in enumerate(seq):
    name=slots[(10+i)%15];label='%02X(%s)'%(ip,name)
    prove(p,address(b)==ip,label+' is forced')
    out=[];b=ex(b,ip,*keys('quiet_store_'+str(i)),serial_inputs=pages[slots[(11+i)%15]],emitted_outputs=out)
    if ip==0xD4:
        assert name=='P7'
        prove(p,And(*[out[3*j]==source[j] for j in range(12)],
                    *[out[j]==pages[name][j] for j in range(42) if j%3!=0 or j>=36]),
              label+' writes only twelve exact source tetras to M1/P4')
    else:prove(p,And(*[x==y for x,y in zip(out,pages[name])]),label+' holds all 42 ring tetras')
prove(p,address(b)==0xA5,'returns A5')
print('PASS: 32 connected commands, arbitrary X -> ordinary P4, no M2/M3 writes.',flush=True)
print('LIMIT: accepted Q and marker placements are conditional; native keys and the later return are tested separately.',flush=True)
