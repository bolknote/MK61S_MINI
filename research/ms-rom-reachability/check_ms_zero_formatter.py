#!/usr/bin/env python3
"""Discover and prove the exact zero EE-to-40 path, then its W/marker return.

The zero is exact, while other entry fields, keys and serial inputs stay
arbitrary. This is a local formatter contract, not keyboard reachability.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys,values=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys','possible_values'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()

a=State('zero_format');p=base(a,0xEE)
p.add(a.s1==13,a.r[38]==12,a.r[41]==15,
      ZeroExt(4,a.st[36])|(ZeroExt(4,a.st[39])<<4)==0xE3,
      *[a.m[1+3*j]==0 for j in range(12)])
b=a;seq=[]
for i in range(120):
    p.push();ips=values(address(b),p,2);p.pop()
    assert len(ips)==1,('ambiguous next address',i,ips)
    ip=ips[0]
    if ip==0x40:break
    seq.append(ip);previous=b.m;out=[]
    b=ex(b,ip,*keys('zero_normal_'+str(i)),emitted_outputs=out)
    prove(p,And(*[x==y for x,y in zip(out,previous)]),'no normalizer writes at %02X'%ip)
else:raise AssertionError('zero normalizer does not terminate within bound')
prove(p,And(*[b.r[3*j]==0 for j in range(12)]),'zero source survives normalization')
print('PASS zero normalizer:',len(seq),'commands;',' '.join('%02X'%ip for ip in seq),flush=True)
first=(slots.index('P8')+len(seq))%15;form=[];destination=None
for i in range(60):
    name=slots[(first+i)%15]
    p.push();ips=values(address(b),p,2);p.pop()
    assert len(ips)==1,('ambiguous formatter address',i,ips)
    ip=ips[0]
    if ip==0x47:break
    form.append(ip)
    if ip==0xE5:p.add(b.m[22]==15 if name in ('marker','W') else b.m[22]!=15)
    prove(p,address(b)==ip,'forced formatter %02X(%s)'%(ip,name))
    previous=b.m;out=[];b=ex(b,ip,*keys('zero_return_'+str(i)),emitted_outputs=out)
    if ip==0xE7:
        assert destination is None;destination=name
        prove(p,And(*[out[1+3*j]==0 for j in range(12)],
                    *[out[j]==previous[j] for j in range(42) if j%3!=1 or j>=37]),'only exact twelve-tetra zero write')
    else:prove(p,And(*[x==y for x,y in zip(out,previous)]),'no preceding return writes')
else:raise AssertionError('zero formatter does not return within bound')
prove(p,address(b)==0x47,'returns 47')
assert destination is not None
print('PASS return path:',' '.join('%02X'%ip for ip in form),flush=True)
print('PASS EE(P8=0) with only W and original marker: zero is written to',destination,flush=True)
print('LIMIT: this does not prove native entry, quiet other chips or the effect of keys before/after the formatter.',flush=True)
