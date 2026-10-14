#!/usr/bin/env python3
"""Why recalling zero P3 survives the two possible preliminary M2 reads.

Conditional chip contracts with arbitrary per-tick keys and serial input.
Native tests separately establish ring positioning and all-chip behavior.
"""
import runpy
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

# Recall opcode 63 enters AB even if the preceding EE read the false X
# instead of W. The accumulator is deliberately unconstrained here.
a=State('zero_lift_decode');p=base(a,0xAB);p.add(a.r[32]==3,a.r[35]==6);b=a
for i,ip in enumerate([0xAB,0xAD,0xA6]):
    prove(p,address(b)==ip,'opcode 63 forces entry %02X independent of the old M2 word'%ip)
    b=execute(b,ip,*keys('zero_lift_decode_keys_%d'%i))
prove(p,And(address(b)==1,b.s1==6,stack(b)[0]==0xA7,b.r[35]==3),
      'register recall selects M1 load body 6, return A7, and register digit 3')

# Unbounded alignment waits cannot redirect this selector through C9/BC.
for ip,targets in [(1,[1,2]),(2,[2,3]),(3,[4]),(4,[0xBA]),
                   (0xBA,[0xCB]),(0xCB,[0xDD]),(0xDD,[0xD6])]:
    a=State('zero_lift_helper_%x'%ip);p=base(a,ip);p.add(a.s1==6)
    out=[];b=execute(a,ip,*keys('zero_lift_helper_keys_%x'%ip),emitted_outputs=out)
    prove(p,And(Or(*[address(b)==target for target in targets]),b.s1==6,
                *[x==y for x,y in zip(stack(b),stack(a))],b.r[35]==a.r[35],
                *[out[j]==a.m[j] for j in range(42)]),
          '%02X preserves selector/return/register digit and does not write the ring'%ip)

# D6 is read-only and completely replaces the previous A: no digit from
# the accidental preliminary M2 read survives as the zero pushed into X.
a=State('zero_lift_d6');p=base(a,0xD6);out=[]
b=execute(a,0xD6,*keys('zero_lift_d6_keys'),emitted_outputs=out)
prove(p,And(*[b.r[3*i]==a.m[3*i] for i in range(12)],
            *[out[j]==a.m[j] for j in range(42)],address(b)==stack(a)[0]),
      'D6 replaces ALL twelve A tetras from M1 and returns without writing memory')

# In the native reference P3 occupies the M1 lane of Q. From that real
# position the following search starts at P8, after the false X/T markers.
# Assume no F marker in P8/P9/P10, as checked for the ordinary Ms fixtures.
names=['Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T','U','V']
seq=[0xD6,0xA7,0xE5,0xE5,0xE5,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
pages=[State('zero_lift_page_'+s).m for s in names]
a=State('zero_lift_positioned');a.m=pages[0];p=base(a,0xD6)
p.add(stack(a)[0]==0xA7,stack(a)[1]==0xAC,
      *[a.m[3*i]==0 for i in range(12)],
      *[pages[i][22]!=15 for i in [2,3,4]],pages[5][22]==15)
b=a;entries=[]
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'positioned zero lift at %s executes %02X'%(names[i],ip))
    entries.append(b);out=[]
    b=execute(b,ip,*keys('zero_lift_positioned_keys_%d'%i),
              serial_inputs=pages[i+1],emitted_outputs=out)
    if 8<=i<=11:
        incoming=[q['N4'](0)]*12 if i==8 else [pages[i-1][1+3*j] for j in range(12)]
        prove(p,And(*[out[1+3*j]==incoming[j] for j in range(12)],
                    *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],
                    *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
              'zero lift writes only the twelve numeric M2 tetras at '+names[i])
    else:
        prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),
              'zero lift preserves all 42 memory tetras at '+names[i])
prove(p,And(address(b)==0xAC,b.s1==0),
      'finite stack lift returns to AC, independent of U/V exponents or preliminary EE contents')
print('NOT a universal keyboard theorem: native tests supply opcode 63, zero P3, the physical Q position and the marker-placement premises.',flush=True)
