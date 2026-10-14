#!/usr/bin/env python3
"""Exact 60 -> eight A8 swaps -> A9 -> 6E contracts, not keyboard timing."""
import runpy
from pathlib import Path
from z3 import And, sat, unsat, ZeroExt

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
a=q['State']('a8_bank_gate')
p=q['base_solver'](a,0x60)
p.add(a.r[38]==2,a.r[25]==a.r[31],byte(a.st[36],a.st[39])==0x6E)
pages=[q['State'](f'a8_bank_page_{i}').m for i in range(9)]
b=q['execute_command'](a,0x60,*q['arbitrary_keys']('a8_bank_gate_keys'),serial_inputs=pages[0])

def prove(claims,label):
    assert p.check()==sat,label
    p.push();p.add(~And(*claims));assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

prove([address(b)==0xA8,b.s1==0]+[b.r[3*i]==a.r[3*((i+1)%12)] for i in range(12)],
      '60 with selector 2 and equal counters enters A8(S1=0), rotating A once')
initial_word=[b.r[3*i] for i in range(12)]
for number in range(8):
    before=b;out=[]
    b=q['execute_command'](before,0xA8,*q['arbitrary_keys'](f'a8_bank_keys_{number}'),
                           serial_inputs=pages[number+1],emitted_outputs=out)
    expected=initial_word if number==0 else [pages[number-1][1+3*i] for i in range(12)]
    prove([address(b)==(0xA9 if number==7 else 0xA8),b.s1==((number+1)*2)%16]+
          [out[1+3*i]==expected[i] for i in range(12)]+
          [b.r[3*i]==pages[number][1+3*i] for i in range(12)]+
          [out[i]==pages[number][i] for i in range(42) if i%3!=1 or i>=37],
          f'A8 pass {number+1}: full twelve-tetrade transfer, all other output tetras unchanged')
before=b
b=q['execute_command'](before,0xA9,*q['arbitrary_keys']('a8_bank_exit_keys'))
prove([address(b)==0x6E]+[b.r[3*i]==before.r[3*i] for i in range(10)]+
      [b.r[30]==before.r[32],b.r[33]==before.r[35]],
      'A9 returns to 6E but replaces the last two A tetras; this is not a lossless bank-swap return')
at_a9=before
b=q['execute_command'](b,0x6E,*q['arbitrary_keys']('a8_bank_post_exit_keys'))
prove([address(b)==0x61]+[b.r[3*i]==at_a9.r[1+3*i] for i in range(8)]+
      [b.r[24]==15,b.r[27]==at_a9.r[27],
       b.r[30]==at_a9.r[32],b.r[33]==at_a9.r[35]],
      'A9/6E replace the last word mantissa from B and sign with F; '
      'only its exponent-units tetra remains unchanged in A')
