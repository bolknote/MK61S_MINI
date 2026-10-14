#!/usr/bin/env python3
"""Bounded secondary 14 request with only the normal marker present.

Compare a decimal payload behind control=14 with the all-zero payload.
The ring is connected and updated at every command. No unknown branch is
silently selected. This does not prove how the keyboard reaches this state.
"""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, ULE, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('analyze_ms_pending_opcodes.py')))
State,ex,base,keys=(q[n] for n in ('State','ex','base','keys'))
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);r=p.check()
    assert r==unsat,(label,p.model() if r==sat else r)
    p.pop()

a=State('control_normal14');p=base(a,0x6E);p.add(a.r[29]==0)
pages=[State('control_normal14_'+name).m for name in slots]
for i,page in enumerate(pages):p.add(page[22]==15 if i==0 else page[22]!=15)
p.add(pages[1][34]==1,pages[1][31]==4)
for j in range(10):p.add(ULE(pages[1][1+3*j],9))
other=[list(page) for page in pages]
for j in range(10):other[1][1+3*j]=BitVecVal(0,4)
a.m=pages[0];b=a.copy();original_control=list(pages[1]);path=[]
for step in range(45):
    p.push();ips=q['q']['possible_values'](addr(a),p,257);p.pop()
    assert len(ips)==1,('non-forced path',path,ips)
    ip=ips[0];prove(p,addr(b)==ip,'same dispatch address')
    if step and ip==0x6E:break
    here=step%15;following=(here+1)%15;path.append('%02X(%s)'%(ip,slots[here]))
    signals=keys('normal14_keys_'+str(step));oa=[];ob=[]
    a=ex(a,ip,*signals,serial_inputs=pages[following],emitted_outputs=oa)
    b=ex(b,ip,*signals,serial_inputs=other[following],emitted_outputs=ob)
    if here==1:
        prove(p,And(*[oa[i]==ob[i] for i in range(42) if i not in [1+3*j for j in range(10)]]),
              'control differs only in the original ten numeric payload tetras')
        prove(p,And(*[oa[1+3*j]==original_control[1+3*j] for j in range(10)]),
              'control payload is preserved')
    else:prove(p,And(*[x==y for x,y in zip(oa,ob)]),'all other emitted ring tetras are identical')
    prove(p,And(*[x==y for i,(x,y) in enumerate(zip(a.r,b.r)) if i!=23],
                *[x==y for x,y in zip(a.st,b.st)],
                *[getattr(a,n)==getattr(b,n) for n in ('s','s1','l','t','carry')]),
          'all internal state except the declared residual R23 remains identical')
    pages[here]=oa;other[here]=ob
else:raise AssertionError(('no bounded 14 return',path))
prove(p,And(addr(a)==0x6E,a.r[29]==0,pages[1][34]==1,pages[1][31]==15),'normal 14 returns with ACK 1F')
print('PASS: normal-marker 14 request, arbitrary decimal control payload, fixed connected route:', ' -> '.join(path),flush=True)
print('PASS: same ring output outside the original control payload and same chip state except residual R23; control ends 1F.',flush=True)
print('LIMIT: conditional secondary contract only; not W removal, IK1306, arbitrary future arithmetic, or a native keyboard exit.',flush=True)
