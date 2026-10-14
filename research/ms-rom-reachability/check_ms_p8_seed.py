#!/usr/bin/env python3
"""Local ROM suffix: retained ordinary P8 seeds U and moves the U marker to V.

Native entry establishes D6 at the physical marker and a false marker in Y.
The source's twelve tetras, other page data and key signals stay arbitrary.
This does not claim that every seeded number permits the later control scan.
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
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()

a=State('p8_seed_decode');p=base(a,0xAB);p.add(a.r[32]==8,a.r[35]==6);b=a
for i,ip in enumerate([0xAB,0xAD,0xA6]):
    prove(p,address(b)==ip,'68 decode %02X'%ip)
    b=ex(b,ip,*keys('p8_decode_'+str(i)))
prove(p,And(address(b)==1,b.s1==6,stack(b)[0]==0xA7,b.r[35]==8),'68 selects M1 index 8, return A7')
names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8']
seq=[0xD6,0xA7,0xE5,0xE5,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
pages=[State('p8_seed_page_'+n).m for n in names]
a=State('p8_seed');a.m=pages[0];p=base(a,0xD6)
p.add(stack(a)[0]==0xA7,stack(a)[1]==0xAC,pages[2][22]!=15,pages[3][22]!=15,pages[4][22]==15)
b=a;source=[pages[0][3*i] for i in range(12)]
for i,ip in enumerate(seq):
    label='%02X(%s)'%(ip,names[i]);prove(p,address(b)==ip,label+' forced command')
    out=[];b=ex(b,ip,*keys('p8_seed_'+str(i)),serial_inputs=pages[i+1],emitted_outputs=out)
    if 7<=i<=10:
        incoming=source if i==7 else [pages[i-1][1+3*j] for j in range(12)]
        prove(p,And(*[out[1+3*j]==incoming[j] for j in range(12)],
                    *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],
                    *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
              label+' swaps exactly 12 numeric tetras, preserves displaced word and every other tetra')
    else:prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),label+' no ring writes')
    if i<7:prove(p,And(*[b.r[3*j]==source[j] for j in range(12)]),label+' retained source')
prove(p,And(address(b)==0xAC,b.s1==0),'finite return')
print('PASS: 68 decode and 12-command D6(marker)..AC suffix; P8 -> U, old U/V/W -> V/W/Q; all 48 numeric writes exact; no M1 or service writes.',flush=True)
print('LIMIT: later entry with arbitrary seeded U is not proved; the composition uses its original in-domain U backup.',flush=True)
