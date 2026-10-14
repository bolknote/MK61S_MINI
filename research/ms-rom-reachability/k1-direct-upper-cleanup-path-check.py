#!/usr/bin/env python3
"""Conditional LastX suffix with only the extra U marker.

The native counterexample supplies EE(W), stack tags and zero work fields.
Payloads and key signals below are arbitrary. This is not a whole-keyboard
theorem or a proof that other cleanup strategies are impossible.
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
seq=[0xEE,0xF0,0xE0,0xA7,0xE5,0xE5,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
names=[slots[(9+i)%15] for i in range(len(seq)+1)]
pages={n:State('direct_lastx_page_'+n).m for n in slots}
a=State('direct_lastx');a.m=pages['W'];p=base(a,0xEE)
p.add(a.s1==14,a.r[23]==0,a.r[26]==0,a.r[29]==0,
      *[x==y for x,y in zip(stack(a),[0xF0,0x8E,0x9A])])
for n in slots:p.add(pages[n][22]==15 if n in ('marker','U') else pages[n][22]!=15)

def prove(claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()

b=a;carried=[pages['W'][1+3*j] for j in range(12)];written={}
for i,ip in enumerate(seq):
    label='%02X(%s)'%(ip,names[i]);prove(address(b)==ip,label+' forced next address')
    out=[];b=ex(b,ip,*keys('direct_lastx_keys_'+str(i)),
                serial_inputs=pages[names[i+1]],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                  *[out[j]==pages[names[i]][j] for j in range(42) if j%3!=1 or j>=37]),
              label+' exactly twelve numerical writes')
        written[names[i]]=out;carried=[pages[names[i]][1+3*j] for j in range(12)]
    else:prove(And(*[x==y for x,y in zip(out,pages[names[i]])]),label+' no ring writes')
    if ip==0xA8 and names[i]=='T':
        prove(And(*[b.r[3*j]==pages['T'][1+3*j] for j in range(12)]),
              'old T is displaced into A, not another ring word')
assert list(written)==['X','Y','Z','T']
prove(And(address(b)==0xE1,
          *[written[n][1+3*j]==pages[old][1+3*j]
            for n,old in [('X','W'),('Y','X'),('Z','Y'),('T','Z')] for j in range(12)]),
      'W is read, visible stack rises, hidden U marker stays')
print('PASS 14 connected commands: W -> X, old X/Y/Z -> Y/Z/T; old T displaced, all banks and U marker unchanged.',flush=True)
print('LIMIT: conditional suffix; native entry and late formatting checked separately. Not general impossibility of cleanup or K1.',flush=True)
