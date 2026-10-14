#!/usr/bin/env python3
"""Exact local header-one suffix: numeric ST at D2 and cache erasure.

Arbitrary DC chip fields, physical per-tick keys and future serial inputs.
This is a suffix contract, not a native reachability or K2 exclusion proof.
"""
from pathlib import Path
import runpy
from z3 import And, BitVec, Or, UGE, ULE, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
checker=runpy.run_path(str(root/'verify_c8_recovery_candidate.py'),
                      init_globals={'transport':{'q':q}})
bridge=[int(v,16)for v in
  '8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D'.split()]
first=checker['verify_sequence'](bridge)
assert first['result']==sat
fa=first['initial'];fb=first['states'][-1]
saved=[v for j in range(0,36,3)
       for v in (fa.r[j+1],fa.r[j+2],fa.st[j+(1 if j<27 else 2)])]
fp=first['solver'];fp.push()
fp.add(~And(*[x==y for x,y in zip(fb.st[:36],saved)]))
assert fp.check()==unsat;fp.pop()
for ip in (0x8D,0x4F,0xAF,0xAE,0xDC):
    unchanged=q['State'](f'cache_tail_st_hold_{ip}')
    after=q['execute_command'](unchanged,ip,*q['arbitrary_keys'](f'cache_tail_st_hold_keys_{ip}'))
    hold=q['base_solver'](unchanged,ip)
    hold.add(~And(*[x==y for x,y in zip(after.st[:36],unchanged.st[:36])]))
    assert hold.check()==unsat
print('PASS the earlier 8C double restore leaves numeric ST from old B/C/ST, '
      'with no old A tetras. 8D/4F/AF/AE/DC do not modify numeric ST.',flush=True)
sequence=[int(v,16)for v in
  'DC DE D1 91 92 93 94 95 98 9A 93 94 95 98 9A D2 30'.split()]
r=checker['verify_sequence'](sequence,constraints=lambda a:[a.r[34]==1])
assert r['result']==sat
a=r['initial'];at_d2=r['states'][-2];after_d2=r['states'][-1];p=r['solver']
expected=[]
for j in range(0,36,3):
    middle=0 if j<21 or j==24 else 7 if j==21 else a.r[j+2]
    expected.extend((a.r[j+1],middle,a.st[j+1]))
p.push();p.add(~And(*[v==w for v,w in zip(at_d2.st[:36],expected)]))
assert p.check()==unsat;p.pop()
p.push();p.add(~And(*[v==w for v,w in zip(after_d2.st[:36],expected)]))
assert p.check()==unsat;p.pop()
print('PASS D2 numeric ST triples:',flush=True)
print('  ST[3i..3i+2] = (DC.R[3i+1], 0, DC.ST[3i+1]) for i=0..6,8',flush=True)
print('  ST21..23 = (DC.R22,7,DC.ST22)',flush=True)
print('  ST27..29 = (DC.R28,DC.R29,DC.ST28)',flush=True)
print('  ST30..32 = (DC.R31,DC.R32,DC.ST31)',flush=True)
print('  ST33..35 = (DC.R34=1,DC.R35,DC.ST34)',flush=True)
print('  D2 preserves all 36 numeric ST cells.',flush=True)

# Same complete signal/input streams in two executions differing only in the
# six raw DC A tetras. No independent external ring is a payload reserve here.
positions=(0,3,9,12,18,21)
b=a.copy();d=a.copy()
for pos in positions:d.r[pos]=BitVec(f'cache_tail_d2_alternative_{pos}',4)
p=q['base_solver'](a,0xDC);p.add(a.r[34]==1)
for i,ip in enumerate(sequence[:-1]):
    xs,ys=r['key_pins'][i]
    for x,y in zip(xs,ys):
        p.add(Or(And(x==0,y==0),And(UGE(x,2),ULE(x,11),Or(y==1,y==8,y==9))))
    serial=q['State'](f'cache_tail_d2_serial_{i}').m
    b=q['execute_command'](b,ip,xs,ys,serial_inputs=serial)
    d=q['execute_command'](d,ip,xs,ys,serial_inputs=serial)
    p.add(checker['address'](b)==sequence[i+1],checker['address'](d)==sequence[i+1])
assert p.check()==sat
claims=[x==y for group in ('r','m','st')for x,y in
        zip(getattr(b,group),getattr(d,group))]
claims.extend(getattr(b,n)==getattr(d,n)for n in ('s','s1','l','t','carry'))
p.add(~And(*claims))
assert p.check()==unsat,p.reason_unknown()
print('PASS after D2, every IK1302 R/ST/M/scalar is independent of the six '
      'old DC A cache tetras on a shared future ring stream.',flush=True)
print('LIMIT: original bytes still exist in program memory; only this suffix '
      'and these six internal cache tetras are covered.',flush=True)
