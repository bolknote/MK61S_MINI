#!/usr/bin/env python3
"""Why the newly displaced word cannot be recovered after E7 -> 47.

This is a local IK1302 information-loss contract. It does not exclude an
independent copy made before E7, or a different entry/return path.
"""
import runpy
from pathlib import Path
from z3 import And, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))

def same(a,b):
    return And(*[x==y for n in ('r','st','m') for x,y in zip(getattr(a,n),getattr(b,n))],
               *[getattr(a,n)==getattr(b,n) for n in ('s','s1','l','t','carry')])

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

a=State('discard47');b=a.copy();other=State('discard47_other')
for i in range(12): b.r[3*i]=other.r[3*i]
k=keys('discard47_keys');serial=State('discard47_serial').m
out_a=[];out_b=[]
aa=ex(a,0x47,*k,serial_inputs=serial,emitted_outputs=out_a)
bb=ex(b,0x47,*k,serial_inputs=serial,emitted_outputs=out_b)
prove(base(a,0x47),And(same(aa,bb),*[x==y for x,y in zip(out_a,out_b)]),
      '47 completely discards differences in all twelve incoming A tetras, even under arbitrary keys')
prove(base(a,0x47),And(*[aa.r[3*i]==a.st[3*i] for i in range(12)],
                      *[out_a[i]==a.m[i] for i in range(42)]),
      '47 replaces A by the old ST numeric lane without writing the ring')

a=State('swap_discard');b=a.copy();other=State('swap_discard_other')
for i in range(12):b.m[1+3*i]=other.m[1+3*i]
p=base(a,0xE7);p.add(a.st[36]==7,a.st[39]==4)
for index,ip in enumerate((0xE7,0x47)):
    k=keys('swap_discard_keys_'+str(index));serial=State('swap_discard_serial_'+str(index)).m
    out_a=[];out_b=[]
    a=ex(a,ip,*k,serial_inputs=serial,emitted_outputs=out_a)
    b=ex(b,ip,*k,serial_inputs=serial,emitted_outputs=out_b)
    prove(p,And(*[x==y for x,y in zip(out_a,out_b)]),'no displaced-word difference reaches the ring at %02X'%ip)
prove(p,same(a,b),'E7 returning to 47 leaves the same whole IK1302 state for any two displaced numeric words')
print('No earlier independent copy and no alternative return are ruled out by this local contract.',flush=True)
