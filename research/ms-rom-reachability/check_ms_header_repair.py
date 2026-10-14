#!/usr/bin/env python3
"""Exact header writer and its startup/keyboard boundary.

These are local contracts, not a found U-repair keyboard sequence.
Active rows 2..11 form a superset of all single keys of the reference;
even asynchronous row/column changes are permitted at every microtick.
"""
import runpy
from pathlib import Path
from z3 import And, Or, UGE, ULE, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
A=lambda a:[a.r[i] for i in range(0,36,3)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

a=State('header_writer_34');p=base(a,0x34);out=[]
b=execute(a,0x34,*keys('header_writer_34_keys'),emitted_outputs=out)
prove(p,And(address(b)==0xE2,*[x==y for x,y in zip(A(b),A(a))],
            *[out[i]==(a.r[i-1] if i in (28,31,34) else a.m[i]) for i in range(42)]),
      '34 writes exactly M28/M31/M34 from R27/R30/R33, preserves A and exits to E2')

a=State('header_writer_33');xs,ys=keys('header_writer_33_keys')
b=execute(a,0x33,xs,ys);p=base(a,0x33)
p.push();p.add(address(b)==0x34)
assert p.check()==sat,'unconstrained-key positive control must expose the spurious edge'
p.pop()
p.add(*[Or(y==0,And(UGE(x,2),ULE(x,11))) for x,y in zip(xs,ys)])
prove(p,address(b)!=0x34,
      '33 cannot enter 34 under real single-key row bounds, even with per-tick signal changes')

# A real predecessor is 32, but its reset caller destroys the data that a
# repair would need. Follow connected states, not separate arbitrary A's.
a=State('header_writer_startup');p=base(a,0);b=a
for i,ip in enumerate((0,0x32,0x34)):
    prove(p,address(b)==ip,'startup suffix reaches %02X'%ip)
    current=b;out=[]
    b=execute(b,ip,*keys('header_writer_startup_keys_'+str(i)),emitted_outputs=out)
    prove(p,And(*[n==15 for n in A(b)]),'startup %02X leaves every A tetra F'%ip)
    if ip in (0x32,0x34):
        indices=list(range(1,28,3)) if ip==0x32 else [28,31,34]
        prove(p,And(*[out[j]==(15 if j in indices else current.m[j]) for j in range(42)]),
              'startup %02X writes only its fixed F tetras, not a saved U value'%ip)
prove(p,address(b)==0xE2,'startup header suffix exits to E2')
print('Local contracts only: use check_ms_header_entry.py to bound all reset-reachable predecessors/returns.',flush=True)
