#!/usr/bin/env python3
"""Exact CC/BB/BC gate and the closed post-C9 continuation.

All proofs allow arbitrary data, serial input and independently changing key
pins at every tick. Artificial entry parameters are not keyboard protocols.
"""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, Or, UGE, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:q['ZeroExt'](4,lo)|(q['ZeroExt'](4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]


def prove(p,claim,label):
    p.push();p.add(~claim)
    assert p.check()==unsat,label
    p.pop();print('PASS:',label,flush=True)


a=State('cc_gate');b=execute(a,0xCC,*keys('cc_gate_keys'));p=base(a,0xCC)
prove(p,And(address(b)==If(UGE(a.s1,10),BitVecVal(0xBB,8),BitVecVal(0xCD,8)),
            *[b.r[i]==a.r[i] for i in range(1,42,3)],b.s1==a.s1),
      'CC: S1>=A selects BB; otherwise CD; all 14 B tetras survive')

# Closed selector-9 addressing helper. The 01/02 waits may be arbitrarily
# long; none of their iterations can change S1 or escape to a different body.
helper={0x01:{0x01,0x02},0x02:{0x02,0x03},0x03:{0x04},0x04:{0xBA},
        0xBA:{0xCC},0xCC:{0xCD},0xCD:{0xC9}}
for ip,targets in helper.items():
    a=State(f'helper_{ip}');b=execute(a,ip,*keys(f'helper_keys_{ip}'));p=base(a,ip)
    p.add(a.s1==9)
    prove(p,And(b.s1==9,Or(*[address(b)==target for target in targets]),
                *[x==y for x,y in zip(stack(b),stack(a))],b.r[26]==a.r[26]),
          f'{ip:02X}: selector-9 helper is closed; stack and R26 preserved')
for ip,tag in ((0x05,0x06),(0x66,0x67)):
    a=State(f'helper_start_{ip}');b=execute(a,ip,*keys(f'helper_start_keys_{ip}'));p=base(a,ip)
    prove(p,And(address(b)==1,b.s1==9,stack(b)[0]==tag,b.r[26]==a.r[26]),
          f'{ip:02X}: sets selector 9 and return {tag:02X}, irrespective of keys/data')

# Inductive control cover starting immediately after C9 returned to 67.
# Each node's outgoing values imply the next node's precondition. R2 and
# R29 are unrestricted. This proves closure, not termination of ring waits.
island={
    0x67:({0x6A},None,{9}),
    0x6A:({0x6B},{8,9},{8,9}),
    0x6B:({0x6C},{8,9},{8,9}),
    0x6C:({0x68,0x69},{8,9},{8,9}),
    0x69:({0x6A,0xFB},{8,9},{8,9}),
    0x68:({0x05,0x69},{8,9},{8,9}),
    0xFB:({0xFC,0xFD},None,None),
    0xFD:({0xFE},None,None),
    0xFE:({0xFC},None,None),
    0xFC:({0x68},None,{8}),
}
for ip,(targets,selectors,output_selectors) in island.items():
    a=State(f'island_{ip}');b=execute(a,ip,*keys(f'island_keys_{ip}'));p=base(a,ip)
    p.add(a.r[26]!=0,a.r[38]==8)
    if selectors is not None:p.add(Or(*[a.s1==n for n in selectors]))
    claim=And(Or(*[address(b)==target for target in targets]),b.r[26]==a.r[26],
              b.r[38]==8,*[x==y for x,y in zip(stack(b),stack(a))])
    if output_selectors is not None:claim=And(claim,Or(*[b.s1==n for n in output_selectors]))
    prove(p,claim,f'{ip:02X}: closed C9 island for nonzero R26, R38=8')
print('PASS: from 67 with R26!=0,R38=8, execution stays in this island or '+
      'the 05 selector-9 helper until C9. No BB/BC, independent of keys or payload.',flush=True)

# Inspect other aligned full-word write inlets, without asserting that their
# required R29 values can be prepared at these entries by calculator keys.
for selector,sequence in ((10,[0xB1,0xB3,0xBA,0xCC,0xBB,0xBC]),
                          (11,[0xB1,0xB3,0xBB,0xBC])):
    a=State(f'write_inlet_{selector}');b=a;p=base(a,sequence[0]);p.add(a.r[29]==selector)
    outputs=[]
    for i,ip in enumerate(sequence):
        out=[];b=execute(b,ip,*keys(f'write_inlet_{selector}_{i}'),emitted_outputs=out)
        outputs.append(out)
        if i+1<len(sequence):
            prove(p,address(b)==sequence[i+1],f'R29={selector:X}: {ip:02X}->{sequence[i+1]:02X}')
    prove(p,And(*[outputs[-1][1+3*i]==a.r[1+3*i] for i in range(14)],
                address(b)==stack(a)[0]),
          f'B1/R29={selector:X}: writes the entire initial B word via BC and returns')

for ip,vector in ((0x48,0xAF),(0xA3,0xA3)):
    a=State(f'inlet_vector_{ip}');b=execute(a,ip,*keys(f'inlet_vector_keys_{ip}'));p=base(a,ip)
    prove(p,byte(b.r[37],b.r[40])==vector,
          f'{ip:02X} overwrites the two B-vector tetras with {vector:02X}; not a transparent inlet')

# Only the two source service tetras differ. Their originals still exist in
# circulating Ms; this proves their loss from IK1302's immediate state, not
# information loss from the whole calculator or impossibility of rereading.
a=State('c8_service_loss');other=a.copy();variants=State('c8_service_other')
other.m[37],other.m[40]=variants.m[37],variants.m[40]
b,c=a,other;p=base(a,0xC8);p.add(stack(a)[0]==0x6E)
for i,ip in enumerate((0xC8,0x6E,0x61)):
    inputs=State(f'c8_service_serial_{i}').m;signals=keys(f'c8_service_keys_{i}')
    b=execute(b,ip,*signals,serial_inputs=inputs)
    c=execute(c,ip,*signals,serial_inputs=inputs)
    if i<2:prove(p,And(address(b)==(0x6E,0x61)[i],address(c)==(0x6E,0x61)[i]),
                 f'C8 service-loss comparison follows the actual {ip:02X} continuation')
prove(p,And(*[x==y for group in ('r','m','st')
              for x,y in zip(getattr(b,group),getattr(c,group))],
            *[getattr(b,name)==getattr(c,name) for name in ('s','s1','l','t','carry')]),
      'after C8->6E->61, IK1302 state no longer depends on either source service tetra')
