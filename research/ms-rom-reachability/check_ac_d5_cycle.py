#!/usr/bin/env python3
"""Exact data transport of the observed AC/D5 loop, not a C8 route."""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
wait=State('D5_9B_wait')
wait_p=base(wait,0x9B)
wait_b=execute(wait,0x9B,*keys('D5_9B_wait_keys'))
wait_p.add(~And(*[wait_b.r[i]==wait.r[i] for i in (1,2,31,34)],
                *[wait_b.st[i]==wait.st[i] for i in (1,32,35)]))
assert wait_p.check()==unsat,'9B loop preserves the claimed transport fields'
print('PASS: repeated 9B preserves R1,R2,PC,ST1,ST32,ST35.',flush=True)
a=State('ac_D5_loop')
p=base(a,0xAC)
b=a
seq=[int(v,16) for v in ('AC E2 E5 E6 ED EE E3 91 92 '
     '93 94 95 98 9A 93 94 95 98 9A E4 DE D5 '+
     ' '.join(['9B']*11)+' 9C 9E 9F AA').split()]
ee=None
for i,ip in enumerate(seq):
    p.add(address(b)==ip)
    assert p.check()==sat,(i,ip)
    b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4)
    if ip==0xEE:ee=b
    b=execute(b,ip,*keys(f'ac_D5_loop_{i}'))
p.add(address(b)==0xAC)
assert p.check()==sat
claim=And(ee.m[34]==5,b.r[1]==ee.m[1],b.r[31]==ee.m[31],b.r[34]==5,
          b.r[2]==a.st[1],b.st[1]==a.r[2],
          b.st[32]==a.st[32],b.st[35]==a.st[35])
p.push();p.add(~claim)
assert p.check()==unsat,'AC/D5 loop transport'
p.pop()
print('PASS: AC/D5 loop returns to AC with R1=EE M1, PC=5:(EE M31); '
      'swaps R2 and ST1; exactly preserves ST32 and ST35.',flush=True)
print('Consequently repetition cannot bootstrap zero ST32/ST35 into the '
      'required high/nine saved tail. The 580 header gives PC58, not header 6.',flush=True)
