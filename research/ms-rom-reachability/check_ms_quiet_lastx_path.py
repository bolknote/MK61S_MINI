#!/usr/bin/env python3
"""Local original-ROM last-X read and push, before its later formatter.

This proves a read, not a persistent keyboard readout. Native continuation
must independently check the normal formatter, which can overwrite X.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop();print('PASS:',label,flush=True)

names=['P7','P8','P9','P10','marker','control','X1','X','Y','Z','T','U']
pages={n:State('lastx_page_'+n).m for n in names}
a=State('lastx');a.m=pages['P7'];p=base(a,0xEE)
p.add(a.s1==14,a.r[23]==0,a.r[26]==0,a.r[29]==0,pages['marker'][22]==15,
      *[x==y for x,y in zip(stack(a),[0xF0,0x8E,0x9A])])
b=a;carried=[pages['P7'][1+3*j] for j in range(12)]
seq=[0xEE,0xF0,0xE0,0xA7,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8]
for i,ip in enumerate(seq):
    name=names[i];label='%02X(%s)'%(ip,name)
    prove(p,address(b)==ip,label+' is forced')
    out=[];b=ex(b,ip,*keys('lastx_'+str(i)),serial_inputs=pages[names[i+1]],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                    *[out[j]==pages[name][j] for j in range(42) if j%3!=1 or j>=37]),
              label+' writes exactly twelve carried tetras')
        carried=[pages[name][1+3*j] for j in range(12)]
    else:prove(p,And(*[x==y for x,y in zip(out,pages[name])]),label+' holds all 42 ring tetras')
    prove(p,And(*[b.r[3*j]==carried[j] for j in range(12)]),label+' retains exact carried word')
prove(p,address(b)==0xA9,'returns to A9 after X/Y/Z/T push')
print('LIMIT: conditional eleven-command read/push only. The normal later formatter and keyboard source selection are not covered.',flush=True)
