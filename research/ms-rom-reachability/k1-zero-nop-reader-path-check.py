#!/usr/bin/env python3
"""Conditional W reader: raw visible push drops T's only extra marker.

Prove its complete connected EE->E1 prefix for arbitrary W, then prove
the separate canonical formatter return after the marker is gone. Native
checks cover the keyboard preparation and the interval between the blocks.
This is not a universal proof of the entire keyboard protocol.
"""
import os
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
seq=[0xEE,0xE0,0xA7,0xE5,0xE5,0xE5,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
names=[slots[(9+i)%15] for i in range(len(seq)+1)]
pages=[State('zero_nop_page_'+n).m for n in names]
a=State('zero_nop_read');a.m=pages[0];p=base(a,0xEE)
p.add(byte(a.st[36],a.st[39])==0xE0)
source=[pages[0][1+3*j] for j in range(12)]
for name,page in zip(names,pages):
    if name in ('X','Y','Z'):p.add(*[page[1+3*j]==0 for j in range(12)])
    if name=='T':p.add(*[page[1+3*j]==(15 if j==7 else 0) for j in range(12)])
    if name in ('marker','P8','P9','P10'):p.add(page[22]==15 if name=='marker' else page[22]!=15)
carried=source;b=a;written={}
def prove(claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop()
for i,ip in enumerate(seq):
    label='%02X(%s)'%(ip,names[i]);prove(address(b)==ip,label+' address')
    out=[];b=ex(b,ip,*keys('zero_nop_keys_'+str(i)),serial_inputs=pages[i+1],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                  *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),label+' exact numeric swap')
        written[names[i]]=out;carried=[pages[i][1+3*j] for j in range(12)]
    else:prove(And(*[x==y for x,y in zip(out,pages[i])]),label+' no ring writes')
assert list(written)==['X','Y','Z','T']
prove(And(address(b)==0xE1,*[written['X'][1+3*j]==source[j] for j in range(12)],
          *[written[n][1+3*j]==0 for n in ('Y','Z','T') for j in range(12)]),
      'exact W read, sole extra marker removed, E1 return')
print('PASS 14 connected commands: arbitrary W copied to X; Y/Z/T cleared; no Ms, M1, M3 or service writes.',flush=True)

formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
selected=os.environ.get('K1_READER_FORMAT_CASES')
cases=[tuple(map(int,x.split(','))) for x in selected.split(';')] if selected else [
    (h,z,int(s)) for h in (9,0) for s in ([False] if h==9 else [False,True]) for z in range(8)]
for h,z,s in cases:formatter(h,z,bool(s),source_slot='X',marker_slots=('marker',),target_by_class=('X',)*9)
if not selected:formatter(0,7,True,True,source_slot='X',marker_slots=('marker',),target_by_class=('X',)*9)
print('LIMIT: two local connected blocks. Native preparation, intervening control and other-chip state need separate coverage.',flush=True)
