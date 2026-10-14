#!/usr/bin/env python3
"""Exact return-stack shift behind the keyboard mantissa reader.

All initial data, per-tick key pins and subsequent serial inputs are free.
The keyboard test separately establishes the entry and complete-ring exit.
"""
import runpy
from pathlib import Path
from z3 import And, If, ULT, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
a=q['State']('mantissa_return_shift')
b=a
p=q['base_solver'](a,0x12)
assert p.check()==sat
for i,(ip,nxt) in enumerate(((0x12,0xC6),(0xC6,0x38))):
    b=q['execute_command'](b,ip,*q['arbitrary_keys'](f'mantissa_shift_{i}'))
    p.push();p.add(address(b)!=nxt)
    assert p.check()==unsat,('not a forced edge',ip,nxt)
    p.pop()
p.push()
p.add(~And(*[b.r[7+3*i]==a.r[1+3*i] for i in range(10)]))
assert p.check()==unsat
p.pop()
print('PASS: 12->C6->38 shifts ten R1 nibbles by two positions, including '
      'PC.lo=old R25 and PC.hi=old R28.',flush=True)

for ip,nxt in ((0x38,0x06),(0x06,0x07)):
    b=q['execute_command'](b,ip,*q['arbitrary_keys'](f'mantissa_step_{ip}'))
    p.push();p.add(address(b)!=nxt)
    assert p.check()==unsat,('not a forced edge',ip,nxt)
    p.pop()
p.add(ULT(a.r[25],10),ULT(a.r[28],10))
assert p.check()==sat
expected_lo=If(a.r[25]==9,q['N4'](0),a.r[25]+1)
expected_hi=a.r[28]+If(a.r[25]==9,q['N4'](1),q['N4'](0))
p.add(~And(b.r[31]==expected_lo,b.r[34]==expected_hi,
           *[b.r[7+3*i]==a.r[1+3*i] for i in range(8)]))
assert p.check()==unsat
print('PASS: 12->C6->38->06->07 exposes the old pair plus ONE, including '
      '00->01, 09->10 and 99->A0; the other eight shifted cells survive.',flush=True)
