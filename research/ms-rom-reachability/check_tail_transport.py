#!/usr/bin/env python3
"""Local exact semantics of the newly traced saved-tail source routes."""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, UGE, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda low,high:ZeroExt(4,low)|(ZeroExt(4,high)<<4)
address=lambda a:byte(a.r[36],a.r[39])


def prove(ip,label,claim):
    a=State(f'tail_fact_{ip}')
    b=execute(a,ip,*keys(f'tail_fact_keys_{ip}'))
    p=base(a,ip)
    assert p.check()==sat
    p.add(~claim(a,b))
    assert p.check()==unsat,label
    print('PASS: '+label,flush=True)


prove(0x4E,'4E forms R30/R33 from key nibble R29 and prefix R32; enters 97',
      lambda a,b:And(b.r[30]==a.r[29],b.r[33]==a.r[32],address(b)==0x97))
prove(0x99,'99 takes 74 exactly when the pending-address marker R26 is nonzero',
      lambda a,b:address(b)==If(a.r[26]!=0,BitVecVal(0x74,8),BitVecVal(0x9B,8)))
prove(0x74,'74 copies the raw R30/R33 pair into the PC without BCD normalization',
      lambda a,b:And(b.r[31]==a.r[30],b.r[34]==a.r[33],address(b)==0x86))
prove(0xEC,'EC swaps PC into the next whole-word push input',
      lambda a,b:And(b.r[30]==a.r[31],b.r[33]==a.r[34],address(b)==0x40))
prove(0xB3,'B3 dispatches through R29, clears R23, preserves R30/R33',
      lambda a,b:And(address(b)==(0xB0|ZeroExt(4,a.r[29])),
                    b.r[23]==0,b.r[35]==a.r[29],b.r[38]==8,
                    b.r[30]==a.r[30],b.r[33]==a.r[33]))
prove(0xBE,'BE pushes the three saved tail triples and selects B0 iff R23=0',
      lambda a,b:And(address(b)==If(a.r[23]==0,BitVecVal(0xB0,8),BitVecVal(0x63,8)),
        *[b.st[j+k]==v for j in (27,30,33)
          for k,v in enumerate((a.r[j],a.st[j],a.st[j+1]))],
        *[b.st[j]==a.st[j] for j in range(27)]))
prove(0x48,'48 can take B1 exactly when R32>=4',
      lambda a,b:(address(b)==0xB1)==UGE(a.r[32],4))
prove(0xDD,'DD forms tail R30/R33 from old R33 and the low mantissa nibble R0',
      lambda a,b:And(b.r[30]==a.r[33],b.r[33]==a.r[0]))
prove(0x37,'37 takes 38 exactly when R0,R3,...,R24 are all zero',
      lambda a,b:(address(b)==0x38)==And(*[a.r[i]==0 for i in range(0,27,3)]))
print('PASS: nine reset-independent facts, with arbitrary per-tick keys and serial input.',flush=True)
