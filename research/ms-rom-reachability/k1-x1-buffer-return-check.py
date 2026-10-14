#!/usr/bin/env python3
"""Conditional ROM proof: read buffered X1 through LastX with no false marker.

This is a local connected block, NOT keyboard reachability, a theorem about
arbitrary numerical input or the entire buffer maker, or a solution to K1.
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
seq=[0xEE,0xF0,0xE0,0xA7]+[0xE5]*10+[0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
names=[slots[(2+i)%15] for i in range(len(seq)+1)]
pages={n:State('x1_buffer_page_'+n).m for n in slots}
a=State('x1_buffer_return');a.m=pages['X1'];p=base(a,0xEE)
p.add(a.s1==14,a.r[23]==0,a.r[26]==0,a.r[29]==0,
      *[x==y for x,y in zip(stack(a),[0xF0,0x8E,0x9A])])
for n in slots:p.add(pages[n][22]==15 if n=='marker' else pages[n][22]!=15)
source=[pages['X1'][1+3*i] for i in range(12)]
def prove(claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()
b=a;carried=source;written={}
for i,ip in enumerate(seq):
    label='%02X(%s)'%(ip,names[i]);prove(address(b)==ip,label+' address')
    out=[];b=ex(b,ip,*keys('x1_buffer_keys_'+str(i)),
                serial_inputs=pages[names[i+1]],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                  *[out[j]==pages[names[i]][j] for j in range(42) if j%3!=1 or j>=37]),
              label+' exact twelve-tetra swap')
        written[names[i]]=out
        carried=[pages[names[i]][1+3*j] for j in range(12)]
    else:prove(And(*[x==y for x,y in zip(out,pages[names[i]])]),label+' no writes')
assert list(written)==['X','Y','Z','T']
prove(And(address(b)==0xE1,*[written['X'][1+3*j]==source[j] for j in range(12)],
          *[written[n][1+3*j]==pages[old][1+3*j]
            for n,old in [('Y','X'),('Z','Y'),('T','Z')] for j in range(12)]),
      'exact LastX copy and visible push, original X1 and all stored banks held')
print('PASS 21 connected commands: X1 copied to X, old X/Y/Z lifted, no X1/Ms/M1/M3/service writes.',flush=True)
print('LIMIT: source selection, canonical formatter and whole keyboard preparation need separate evidence.',flush=True)
