#!/usr/bin/env python3
"""Conditional B-source formatter entry to raw M2 exchange.

This constructs no native entry. It shows a useful exact source/control
contract outside the globally absent 98/top46 shortcut. R34=0/9 and R22!=0
are explicit entry requirements. No host calculator state is seeded.
"""
from pathlib import Path
import runpy
from z3 import And, Or, UGE, ULE, sat, unsat

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache-writer-contract.py'))
q=w['q'];State,execute,base,keys=(q[n]for n in
  ('State','execute_command','base_solver','arbitrary_keys'))
address,stack,prove=(w[n]for n in ('address','stack','prove'))

def gate(ip,claim,label):
    a=State(f'cache46_gate_{ip}');b=execute(a,ip,*keys(f'cache46_gate_keys_{ip}'))
    prove(base(a,ip),claim(a,b),label)

gate(0xDC,lambda a,b:And(
  Or(address(b)==0xDE,address(b)==0xEA),
  (address(b)==0xEA)==Or(a.r[34]==0,UGE(a.r[34],9))),
  'DC chooses EA exactly for B-header0 or9..F; DE for1..8')
gate(0xEA,lambda a,b:And(
  Or(address(b)==0xEC,address(b)==0xD8),
  (address(b)==0xEC)==Or(ULE(a.r[34],8),
                       And(a.r[34]==9,Or(a.r[28]!=0,a.r[31]!=0)))),
  'EA chooses EC exactly for header0..8, or9 with B28/B31 nonzero; F alwaysD8')
gate(0x41,lambda a,b:And(
  Or(address(b)==0x42,address(b)==0x43),
  (address(b)==0x42)==Or(*[a.r[j]!=0 for j in range(0,24,3)])),
  '41 chooses42 exactly when at least one of eight low A tetras is nonzero')
gate(0x42,lambda a,b:And(
  Or(address(b)==0x44,address(b)==0x46),
  (address(b)==0x46)==(a.r[21]!=0)),
  '42 chooses46 exactly when A21 is nonzero')

a=State('cache46_B_source');p=base(a,0xDC)
p.add(a.r[22]!=0,Or(a.r[34]==0,
  And(a.r[34]==9,Or(a.r[28]!=0,a.r[31]!=0))))
source=[a.r[1+3*i]for i in range(12)]
seq=(0xDC,0xEA,0xEC,0x40,0x41,0x42,0x46,0xE5,0xE5,0xE6,0xE8,0xE7)
pages=[State(f'cache46_B_page_{i}').m for i in range(len(seq)+1)]
a.m=pages[0];b=a
for i,ip in enumerate(seq):
    if ip==0xE5:p.add(pages[i][22]==(0 if seq[i+1]==0xE5 else 15))
    prove(p,address(b)==ip,f'conditional B-source command {ip:02X} forced',False)
    before=b;output=[]
    b=execute(b,ip,*keys(f'cache46_B_keys_{i}'),
              serial_inputs=pages[i+1],emitted_outputs=output)
    if ip==0xEC:
        prove(p,And(*[b.r[3*j]==source[j]for j in range(12)]),
              'EC transfers all12 original raw B tetras into A')
    if ip==0x40:
        prove(p,And(*[b.st[3*j]==source[j]for j in range(12)]),
              '40 additionally saves all12 raw B-source tetras into numeric ST')
    if ip==0xE7:
        prove(p,And(*[output[1+3*j]==source[j]for j in range(12)],
                    *[output[j]==pages[i][j]for j in range(42)if j%3!=1 or j>=37],
                    *[b.r[3*j]==pages[i][1+3*j]for j in range(12)],
                    address(b)==0x47),
              'E7 exchanges all12 raw B-source tetras with M2, preserves M1/M3/tail, returns47')
    else:
        prove(p,And(*[x==y for x,y in zip(output,pages[i])]),
              f'{ip:02X} prefix has no outgoing ring write',False)
print('POSITIVE CONDITIONAL B-SOURCE, not native:',
      ' '.join(f'{ip:02X}'for ip in seq),'->47',flush=True)
print('ENTRY REQUIREMENTS: source in B; B22!=0; B34=0 or '
      '(B34=9 and (B28!=0 or B31!=0)); marker wait completed.',flush=True)
print('LIMIT: native reader cache is in A, with current DC header1/F. '
      'No keyboard adapter, Ms slot alignment, reverse program write or K2 is proved.',flush=True)
