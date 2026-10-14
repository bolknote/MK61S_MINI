#!/usr/bin/env python3
"""A3 cannot itself retain the overwritten request-header tetras.

Two symbolic primary-chip states differ only in M28/M31/M34. Common
arbitrary key signals and serial inputs produce identical complete output
states and ring outputs. This local fact is not global K1 impossibility;
prior copies elsewhere are deliberately outside its premise.
"""
import runpy
from pathlib import Path
from z3 import And, BitVec, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
a=q['State']('a3_header_a');other=a.copy()
for n in (28,31,34):other.m[n]=BitVec('other_header_'+str(n),4)
signals=q['arbitrary_keys']('shared_a3_keys')
serial=[BitVec('shared_serial_'+str(i),4) for i in range(42)]
out_a=[];out_b=[]
b=q['execute_command'](a,0xA3,*signals,serial_inputs=serial,emitted_outputs=out_a)
c=q['execute_command'](other,0xA3,*signals,serial_inputs=serial,emitted_outputs=out_b)
p=q['base_solver'](a,0xA3)

def prove(claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat,label
    print('PASS',label,flush=True)

for n in (28,31,34):
    p.push();p.add(a.m[n]!=other.m[n]);assert p.check()==sat;p.pop()
prove(And(*[x==y for group in ('r','m','st') for x,y in zip(getattr(b,group),getattr(c,group))],
          *[getattr(b,n)==getattr(c,n) for n in ('s','s1','l','t','carry')],
          *[x==y for x,y in zip(out_a,out_b)]),
      'A3 erases all dependence on old target M28/M31/M34 from every modeled primary state field and ring output')
prove(And(out_a[28]==a.r[27],out_a[31]==a.r[30],out_a[34]==a.r[33],
          *[out_a[i]==a.m[i] for i in range(42) if i not in (28,31,34)]),
      'only the three request-header tetras are replaced; all other ring outputs are held')
print('LIMIT: local A3 equivalence with all other starting fields shared. '
      'Native full-machine collision is tested separately; no universal K1 impossibility.',flush=True)
