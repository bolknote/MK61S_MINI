#!/usr/bin/env python3
"""Exact local output/transport facts. No invented keyboard reachability."""
import runpy
from pathlib import Path
from z3 import And, If, BitVecVal, Or, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda s:ZeroExt(4,s.r[36])|(ZeroExt(4,s.r[39])<<4)

def prove(ip,label,claim):
    a=State('recovery_'+str(ip));b=execute(a,ip,*keys('rk_'+str(ip)))
    p=base(a,ip);assert p.check()==sat;p.add(~claim(a,b))
    assert p.check()==unsat,label
    print('PASS: '+label,flush=True)

prove(0xEC,'EC swaps all 12 numeric nibbles of lanes R0/R1',
      lambda a,b:And(*[b.r[3*i]==a.r[1+3*i] for i in range(12)],
                     *[b.r[1+3*i]==a.r[3*i] for i in range(12)]))
prove(0xEB,'EB always sets L=1 and enters D7; payload choice cannot change this',
      lambda a,b:And(b.l==1,address(b)==0xD7))
prove(0xD7,'D7 enters 7F for L=1 and D9 for L=0',
      lambda a,b:address(b)==If(a.l==1,BitVecVal(0x7F,8),BitVecVal(0xD9,8)))

a=State('recovery_pc');b=execute(a,0x60,*keys('pc60'))
p=base(a,0x60);p.add(address(b)==0x08)
assert p.check()==sat
for ip,nxt in [(0x08,0xEB),(0xEB,0xD7),(0xD7,0x7F)]:
    b=execute(b,ip,*keys('pc'+str(ip)))
    p.push();p.add(address(b)!=nxt);assert p.check()==unsat;p.pop()
p.add(~And(b.r[31]==a.r[25],b.r[34]==a.r[28],
           *[b.r[7+3*i]==a.r[1+3*i] for i in range(8)]))
assert p.check()==unsat
print('PASS: 60->08->EB->D7->7F leaves PC=old R28:R25 and retains eight mantissa nibbles.',flush=True)
print('PASS: the alternative EB->D7->D9 normalization path is impossible, '
      'even with arbitrary per-tick keys and serial input.',flush=True)
