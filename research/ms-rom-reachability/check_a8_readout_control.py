#!/usr/bin/env python3
"""Data provenance of the native U-readout return, not a reachability search.

The connected route is the observed header-0 / U=444 formatter route. Serial
pages and per-tick key signals are otherwise arbitrary. Other formatter
routes are covered only by the separate native examples, not this theorem.
"""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, UGE, ZeroExt, is_true, simplify, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
ROUTE='''
AC E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A
E4 DE D6 E5 E6 E7 AD A7 E5 E6 E8 E7 A8 A8 A8 A9 93 94 95 98 9A
E5 E6 E0 A7 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A
93 94 95 98 9A E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A
93 94 95 98 9A E4 DE D0 F2 F3 F7 F1 F3 F7 F1 F3 F7 F1
F3 F7 F1 F3 F7 F1 F3 F7 F1 F4 F6 F4 F6 F4 F6 F4
EA EC 40 41 42 46 E5 E6 E8 E7 47 49 BD
91 92 93 94 95 98 9A 93 94 95 98 9A BE
'''
sequence=[int(s,16) for s in ROUTE.split()]
a=q['State']('readout_control');p=q['base_solver'](a,0xAC);b=a;entries=[]
for i,ip in enumerate(sequence):
    p.add(address(b)==ip)
    b=b.copy();b.r[36]=q['N4'](ip);b.r[39]=q['N4'](ip>>4)
    entries.append(b)
    b=q['execute_command'](b,ip,*q['arbitrary_keys']('readout_keys_%d'%i))
assert p.check()==sat,'the connected path premise must not be empty'
displaced=entries[33];returned=entries[-1]
assert sequence[33]==0xA8 and sequence[-1]==0xBE
# Structural expression identity, not equality caused by conveniently
# constraining both fields to a fixed number (the earlier R23=7 pitfall).
for dest,source in [(2,1),(5,4),(23,22),(26,25)]:
    assert is_true(simplify(returned.r[dest]==displaced.m[source]))
    p.push();p.add(returned.r[dest]!=displaced.m[source]);assert p.check()==unsat;p.pop()
    print('PASS: BE R%d is exactly old M%d of the last first-block A8 (native T)'%(dest,source),flush=True)
c=q['State']('readout_be');d=q['execute_command'](c,0xBE,*q['arbitrary_keys']('readout_be_keys'))
local=q['base_solver'](c,0xBE)
local.add(address(d)!=If(c.r[23]==0,BitVecVal(0xB0,8),BitVecVal(0x63,8)))
assert local.check()==unsat
print('PASS: with arbitrary per-tick keys BE chooses B0 iff old T leading digit is zero, otherwise 63.',flush=True)
p.push();p.add(displaced.m[22]==0,address(b)!=0xB0);assert p.check()==unsat;p.pop()
p.push();p.add(displaced.m[22]!=0,address(b)!=0x63);assert p.check()==unsat;p.pop()
print('PASS: the connected readout takes the safe B0 edge with the fractional-zero background; INV/sign backgrounds cannot take it.',flush=True)

# A different, earlier guard explains the remaining negative-exponent U
# counterexample. 9B accepts the false T marker; 9C then treats U as its
# candidate control word. No mantissa/sign/key constraints are needed.
c=q['State']('readout_scan_9b');d=q['execute_command'](c,0x9B,*q['arbitrary_keys']('readout_scan_9b_keys'))
local=q['base_solver'](c,0x9B)
local.add(address(d)!=If(c.m[22]==15,BitVecVal(0x9C,8),BitVecVal(0x9B,8)))
assert local.check()==unsat
print('PASS: 9B waits exactly for M22=F, so it accepts the false T marker.',flush=True)
c=q['State']('readout_scan_9c');d=q['execute_command'](c,0x9C,*q['arbitrary_keys']('readout_scan_9c_keys'))
threshold=If(c.m[31]==15,q['N4'](1),q['N4'](7))
local=q['base_solver'](c,0x9C)
local.add(address(d)!=If(UGE(c.m[34],threshold),BitVecVal(0x9E,8),BitVecVal(0x9D,8)))
assert local.check()==unsat
print('PASS: 9C takes 9E iff M34 >= (M31=F ? 1 : 7), regardless of sign/mantissa/keys.',flush=True)
print('For ordinary BCD exponents: header 0 rejects U via 9D; header 9 accepts it via 9E. This is a local guard, not a proof excluding every alternative recipe.',flush=True)
