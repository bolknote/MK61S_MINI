#!/usr/bin/env python3
"""How the address-operation type is constructed and protected around DD."""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
def byte(lo,hi):return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)

count=0
def prove(ip,label,claim):
    global count
    a=State(f'dd_fact_{count}');b=execute(a,ip,*keys(f'dd_keys_{count}'))
    p=base(a,ip);p.add(~claim(a,b))
    assert p.check()==unsat,label
    count+=1
    print('PASS:',label,flush=True)

prove(0x1F,'1F resets the type constructor R32 to zero',lambda a,b:b.r[32]==0)
for ip in (0x18,0x1A,0x1B):
    prove(ip,f'{ip:02X} increments the type constructor R32',lambda a,b:b.r[32]==a.r[32]+1)
prove(0x1C,'1C sets the conditional-branch type R32=2',lambda a,b:b.r[32]==2)
for ip in (0x2C,0xA5,0xAD):
    prove(ip,f'{ip:02X} exchanges R32 and R35',
          lambda a,b:And(b.r[32]==a.r[35],b.r[35]==a.r[32]))
prove(0x1D,'1D enters 25 iff the mode nibble R26=8',
      lambda a,b:(byte(b.r[36],b.r[39])==0x25)==(a.r[26]==8))
prove(0x7E,'7E dispatches through the operation type as 70 OR R35',
      lambda a,b:byte(b.r[36],b.r[39])==(0x70|ZeroExt(4,a.r[35])))

# These commands include the observed address-normalization loop and several
# alternative paths through the same helper. Any repetitions preserve R35 too.
preserving=[0x01,0x02,0x03,0x04,0x06,0x07,0x09,0x20,0x21,0x22,0x23,0x24,
            0x25,0x26,0x28,0x2E,0x2F,0x36,0x37,0x38,0x39,0x3A,
            0x60,0x61,0x62,0x6D,0x6E,0x6F,0xBA,0xCB,0xDD,0xD4,0xD6]
for ip in preserving:
    prove(ip,f'{ip:02X} preserves the operation type R35',lambda a,b:b.r[35]==a.r[35])

def prove_path(sequence,expected,label):
    a=State(label);b=a;p=base(a,sequence[0])
    for index,ip in enumerate(sequence):
        b=execute(b,ip,*keys(f'{label}_keys_{index}'))
        if index+1<len(sequence):p.add(byte(b.r[36],b.r[39])==sequence[index+1])
    assert p.check()==sat,f'{label}: vacuous path'
    p.add(b.r[35]!=expected)
    assert p.check()==unsat,label
    print('PASS:',label,flush=True)

prove_path([0xAD,0xA5],5,'AD->A5 fixes restored R35 at 5, not 7')
prove_path([0x1F,0x1B,0x1D,0x2C],1,'normal indirect store prepares type 1')
prove_path([0x1F,0x1D,0x2C],0,'normal indirect recall prepares type 0')
prove_path([0x1F,0x18,0x1B,0x1D,0x2C],2,'normal indirect jump prepares type 2')
prove_path([0x1F,0x1A,0x18,0x1B,0x1D,0x2C],3,'normal indirect call prepares type 3')
print(f'PASS: {count} one-command DD/type facts and 5 feasible type-construction paths')
