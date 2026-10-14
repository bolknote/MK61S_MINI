#!/usr/bin/env python3
"""Exact data-dependent continuation facts, not assumed keyboard reachability."""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, UGE, ULT, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
N4=lambda n:BitVecVal(n,4)


def prove(ip,label,claim):
    a=State(f'payload_{ip}');b=execute(a,ip,*keys(f'payload_keys_{ip}'))
    p=base(a,ip)
    assert p.check()==sat
    p.add(~claim(a,b))
    assert p.check()==unsat,label
    print('PASS: '+label,flush=True)


prove(0x6E,'6E copies all eight mantissa nibbles into R1 and preserves their R2 source',
      lambda a,b:And(*[b.r[3*i]==a.r[1+3*i] for i in range(8)],
                     *[b.r[1+3*i]==a.r[1+3*i] for i in range(10)]))
prove(0x6E,'6E subtracts three from the loaded PC with low-digit decimal correction',
      lambda a,b:And(b.r[31]==If(ULT(a.r[31],3),a.r[31]+7,a.r[31]-3),
                    b.r[34]==a.r[34]-If(ULT(a.r[31],3),N4(1),N4(0))))
prove(0x61,'61 continues the scan iff the resulting high PC nibble is C..F',
      lambda a,b:address(b)==If(UGE(a.r[34],12),BitVecVal(0x3A,8),BitVecVal(0x63,8)))
prove(0x06,'06 increments a decimal low PC digit modulo ten',
      lambda a,b:If(ULT(a.r[31],10),
                    b.r[31]==If(a.r[31]==9,0,a.r[31]+1),True))

for ip in [0x61,0x3A,0x06,0x07,0x6D,0x60]:
    prove(ip,f'{ip:02X} preserves the eight mantissa nibbles in internal R2',
          lambda a,b:And(*[b.r[1+3*i]==a.r[1+3*i] for i in range(8)]))

a=State('payload_c9');out=[]
b=execute(a,0xC9,*keys('payload_c9_keys'),emitted_outputs=out)
p=base(a,0xC9)
p.add(~And(*[b.r[1+3*i]==a.m[2+3*i] for i in range(14)],
           *[out[2+3*i]==a.r[1+3*i] for i in range(14)]))
assert p.check()==unsat
print('PASS: C9 swaps all 14 R2/M3 nibbles; a paired swap can restore the payload.',flush=True)

a=State('payload_exit');b=execute(a,0x08,*keys('payload_exit08'))
p=base(a,0x08);p.add(address(b)==0xEB)
b=execute(b,0xEB,*keys('payload_exitEB'))
p.add(address(b)==0xD7)
assert p.check()==sat
p.add(~And(*[b.r[7+3*i]==a.r[1+3*i] for i in range(8)]))
assert p.check()==unsat
print('PASS: 08->EB->D7 preserves all eight mantissa nibbles, shifted two R2 positions.',flush=True)

for tens in range(3):
    a=State(f'payload_stride_{tens}');b=a;p=base(a,0xC8)
    p.add(a.r[2]==5,a.r[26]==9,a.r[38]==4,
          a.st[36]==14,a.st[39]==6,
          a.m[25]==0,a.m[31]==tens,a.m[34]==0)
    sequence=[0xC8,0x6E]+[0x61,0x3A,0x06,0x07,0x6D,0x60]*(3-tens)
    assert p.check()==sat
    for i,ip in enumerate(sequence):
        b=execute(b,ip,*keys(f'payload_stride_keys_{tens}_{i}'))
        target=sequence[i+1] if i+1<len(sequence) else 0xC8
        p.push();p.add(address(b)!=target)
        assert p.check()==unsat,(tens,i,ip,target)
        p.pop()
    assert len(sequence)==20-6*tens
    print(f'PASS: positive exponent-tens {tens} forces the next C8 after '
          f'{len(sequence)} commands, independent of all mantissa digits.',flush=True)
