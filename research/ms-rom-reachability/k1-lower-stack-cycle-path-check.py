#!/usr/bin/env python3
"""Conditional connected D6(control) -> AC(P7) preserving push.

The native keyboard test establishes marker X and this physical entry.
Here all twelve source, old T/U/V/W and other page tetras are arbitrary.
This is not a proof of the complete 37-key numeric or timing domain.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
seq=[0xD6,0xA7,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
names=['control','X1','X','Y','Z','T','U','V','W','Q','P7']
pages=[State('tail_cycle_page_'+n).m for n in names]
a=State('tail_cycle');a.m=pages[0];p=base(a,0xD6)
p.add(byte(a.st[36],a.st[39])==0xA7,byte(a.st[37],a.st[40])==0xAC,pages[2][22]==15)
source=[pages[0][3*j] for j in range(12)]
carried=source;written={};b=a
def prove(claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop()
for i,ip in enumerate(seq):
    label='%02X(%s)'%(ip,names[i]);prove(address(b)==ip,label+' forced address')
    out=[];b=ex(b,ip,*keys('tail_cycle_keys_'+str(i)),serial_inputs=pages[i+1],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                  *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),label+' exact numeric swap')
        written[names[i]]=out;carried=[pages[i][1+3*j] for j in range(12)]
        prove(And(*[b.r[3*j]==carried[j] for j in range(12)]),label+' exact displaced word')
    else:prove(And(*[x==y for x,y in zip(out,pages[i])]),label+' no ring writes')
assert list(written)==['T','U','V','W']
for dest,origin in [('U','T'),('V','U'),('W','V')]:
    original=pages[names.index(origin)]
    prove(And(*[written[dest][1+3*j]==original[1+3*j] for j in range(12)]),dest+' carries old '+origin)
prove(And(address(b)==0xAC,b.s1==0),'finite return to AC(P7)')
print('PASS ten connected commands: M1 P9 -> T, old T -> U, old U -> V, old V -> W; exactly 48 numeric writes, all other tetras held.')
print('LIMIT: local arbitrary-word transfer, not whole keyboard preparation, marker cleanup or numeric/timing universality.')
