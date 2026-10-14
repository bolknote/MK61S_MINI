#!/usr/bin/env python3
"""Exact IK1302:9C marker-following control classifier, not key reachability."""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, UGE, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
a=q['State']('control_guard');p=q['base_solver'](a,0x9C)
b=q['execute_command'](a,0x9C,*q['arbitrary_keys']('control_guard_keys'))
address=ZeroExt(4,b.r[36])|(ZeroExt(4,b.r[39])<<4)
accept=If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7))
assert p.check()==sat
p.push();p.add(address!=If(accept,BitVecVal(0x9E,8),BitVecVal(0x9D,8)))
assert p.check()==unsat;p.pop()
print('PASS: 9C accepts iff M34 >= (1 when M31=F, otherwise 7); all other state/data/key signals arbitrary.')
p.push();p.add(a.m[34]==1,a.m[31]==15);assert p.check()==sat
p.add(address!=0x9E);assert p.check()==unsat;p.pop()
print('PASS: W/Q response header 1F is ALWAYS accepted as false control if 9C examines it.')
p.add(a.m[34]==1,a.m[31]==4);assert p.check()==sat
p.add(address!=0x9D);assert p.check()==unsat
print('PASS: the secondary W-reader request 14 in T is rejected as false control; it does not create a 1F U gate.')
