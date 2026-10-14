#!/usr/bin/env python3
"""The real EE read and the first divergence of the AC/A9 candidate."""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])


def prove(p,claim,label):
    assert p.check()==sat,'inconsistent assumptions: '+label
    p.push();p.add(~claim)
    assert p.check()==unsat,label
    p.pop()
    print('PASS: '+label,flush=True)


a=State('wait_E5')
p=base(a,0xE5)
b=execute(a,0xE5,*keys('wait_E5_keys'))
prove(p,And(address(b)==If(a.m[22]==15,BitVecVal(0xE6,8),BitVecVal(0xE5,8)),
            *[b.r[i]==a.r[i] for i in range(42) if i not in (36,39)],
            *[x==y for x,y in zip(b.st,a.st)],b.s1==a.s1,b.s==a.r[41]+12),
      'E5 waits exactly for M22=F; preserves all non-IP R and ST fields and S1; S=R41+C')

a=State('ac_to_DE')
p=base(a,0xAC)
b=a
seq=[int(v,16) for v in ('AC E2 E5 E6 ED EE E3 91 92 '
     '93 94 95 98 9A 93 94 95 98 9A E4').split()]
ee=None
for i,ip in enumerate(seq):
    p.add(address(b)==ip)
    assert p.check()==sat,(i,ip)
    b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4)
    if ip==0xEE:ee=b
    b=execute(b,ip,*keys(f'ac_to_DE_{i}'))
p.add(address(b)==0xDE)
prove(p,And(b.r[1]==ee.m[1],b.r[2]==a.st[1],b.r[34]==ee.m[34],
            b.r[32]==a.st[32],b.r[35]==a.st[35]),
      'before DE: header=EE M34, R2=original ST1, opcode=original ST35:ST32')
de=execute(b,0xDE,*keys('ac_DE'))
prove(p,address(de)==(0xD0|ZeroExt(4,ee.m[34])),
      'DE chooses D0|EE-header; its target is not restricted to normal signs 0/9')
p.add(ee.m[34]==6)
de=de.copy();de.r[36]=q['N4'](0xD6);de.r[39]=q['N4'](0xD)
after_d6=execute(de,0xD6,*keys('ac_D6'))
prove(p,And(address(after_d6)==0xE5,after_d6.s1==a.st[35]),
      'D6 returns to E5 with S1=original ST35; initial numeric header does not set this selector')
after_wait=execute(after_d6,0xE5,*keys('ac_after_D6_wait'))
p.add(address(after_wait)==0xE6)
after_wait=after_wait.copy();after_wait.r[36]=q['N4'](0xE6);after_wait.r[39]=q['N4'](0xE)
after_e6=execute(after_wait,0xE6,*keys('ac_after_D6_E6'))
prove(p,address(after_e6)==(0xE0|ZeroExt(4,a.st[35])),
      'next E6 dispatches on original ST35: zero selects E0, nine is required for E9')
