#!/usr/bin/env python3
"""The direct V-store channel and why the ENTER formatter writes a neighbor.

Conditional ROM contracts, with arbitrary data/serial input/per-tick keys.
Native tests supply the keyboard decode and physical ring-position premises.
"""
import runpy
from pathlib import Path
from z3 import And, Or, If, BitVecVal, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
A=lambda a:[a.r[3*i] for i in range(12)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

# The real-control route puts AA at Y. Its user opcode is still carried in
# the high A pair until AA decodes it into the register-operation fields.
a=State('direct_store_aa');p=base(a,0xAA);p.add(a.r[30]==2,a.r[33]==4)
b=execute(a,0xAA,*keys('direct_store_aa_keys'))
prove(p,And(address(b)==0xE5,b.s1==13,stack(b)[0]==0xAB,b.r[32]==2,b.r[35]==4),
      'AA decodes 42 and starts the +3 M2 read search, with return AB')

# AA starts E5 at Z after the real control scan. Place the false marker
# there: the +3 read offset is V, not U or physical X.
names=['Z','T','U','V','W','Q','P7','P8']
seq=[0xE5,0xE6,0xED,0xEE,0xAB,0xAD,0xA4]
pages=[State('direct_store_page_'+name).m for name in names]
a=State('direct_store_source');a.m=pages[0];p=base(a,0xE5)
p.add(a.s1==13,stack(a)[0]==0xAB,a.r[32]==2,a.r[35]==4,pages[0][22]==15)
b=a
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'positioned source at %s executes %02X'%(names[i],ip))
    out=[]
    b=execute(b,ip,*keys('direct_store_source_keys_%d'%i),
              serial_inputs=pages[i+1],emitted_outputs=out)
    prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),
          '%02X reads/decodes without any ring write'%ip)
    if i>=3:
        prove(p,And(*[v==pages[3][1+3*j] for j,v in enumerate(A(b))]),
              '%02X preserves all twelve source V tetras, without numeric assumptions'%ip)
prove(p,And(address(b)==1,b.s1==4,stack(b)[0]==0xA5),
      'store opcode 42 selects the M1 writer, not a stack lift or formatter')

# Account for every possible duration of the register-address alignment waits.
for ip,targets in [(1,[1,2]),(2,[2,3]),(3,[4]),(4,[0xBA]),(0xBA,[0xCB]),(0xCB,[0xDD])]:
    a=State('direct_store_helper_%x'%ip);p=base(a,ip);p.add(a.s1==4)
    out=[];b=execute(a,ip,*keys('direct_store_helper_keys_%x'%ip),emitted_outputs=out)
    prove(p,And(Or(*[address(b)==target for target in targets]),b.s1==4,
                *[x==y for x,y in zip(A(b),A(a))],
                *[x==y for x,y in zip(stack(b),stack(a))],
                *[out[j]==a.m[j] for j in range(42)]),
          '%02X preserves the complete source and writer selector without ring writes'%ip)

# DD rotates A, and D4's serial write undoes that rotation. Check the pair,
# not a misleading same-index comparison at the intermediate D4 entry.
a=State('direct_store_write');p=base(a,0xDD);p.add(a.s1==4)
next_page=State('direct_store_m1_page').m;out=[]
b=execute(a,0xDD,*keys('direct_store_dd_keys'),serial_inputs=next_page,emitted_outputs=out)
prove(p,And(address(b)==0xD4,*[out[j]==a.m[j] for j in range(42)]),
      'DD selects D4 and does not write its current page')
out=[];c=execute(b,0xD4,*keys('direct_store_d4_keys'),emitted_outputs=out)
prove(p,And(address(c)==stack(a)[0],
            *[out[3*i]==a.r[3*i] for i in range(12)],
            *[out[j]==next_page[j] for j in range(42) if j%3!=0 or j>=36]),
      'DD/D4 writes all twelve original A tetras to M1 and preserves every M2/M3 tetra')

# The rejected ENTER construction does reach the canonical-format writer.
# Its nonzero canonical number cannot bypass that writer by different key
# signals or arbitrary unrelated processor fields at these two gates.
a=State('formatter_nonzero');p=base(a,0x41)
p.add(Or(*[a.r[3*i]!=0 for i in range(8)]))
b=execute(a,0x41,*keys('formatter_nonzero_keys'))
prove(p,address(b)==0x42,'41 sends every nonzero eight-tetra mantissa to 42')
a=State('formatter_canonical');p=base(a,0x42)
b=execute(a,0x42,*keys('formatter_canonical_keys'))
prove(p,address(b)==If(a.r[21]!=0,BitVecVal(0x46,8),BitVecVal(0x44,8)),
      '42 sends a nonzero leading mantissa tetra to 46; zero goes to normalization 44')
a=State('formatter_store');p=base(a,0x46)
b=execute(a,0x46,*keys('formatter_store_keys'))
prove(p,And(address(b)==0xE5,b.s1==8,stack(b)[0]==0x47,
            *[x==y for x,y in zip(A(b),A(a))]),
      '46 preserves the number and launches the marker-relative E7 writer, return 47')
print('NOT a universal keyboard theorem: native tests establish the marker placement, opcode and return/alignment context.',flush=True)
