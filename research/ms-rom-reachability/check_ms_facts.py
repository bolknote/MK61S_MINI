#!/usr/bin/env python3
"""Executable local ROM facts; not a proof of whole-calculator reachability."""
import runpy
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
def byte(lo,hi):return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
count=0
def prove(ip,label,claim):
    global count
    a=State(f'fact_{count}');b=execute(a,ip,*keys(f'fact_keys_{count}'))
    p=base(a,ip);p.add(~claim(a,b))
    assert p.check()==unsat,label
    count+=1
    print('PASS:',label,flush=True)

prove(0xCD,'CD selects C0|S1 and sets R[38]=8',
      lambda a,b:And(byte(b.r[36],b.r[39])==(0xC0|ZeroExt(4,a.s1)),b.r[38]==8))
prove(0x60,'60 enters C8 iff R[25]=R[31] and R[38]=4',
      lambda a,b:(byte(b.r[36],b.r[39])==0xC8)==And(a.r[25]==a.r[31],a.r[38]==4))
prove(0xA3,'A3 jumps through R[37]:R[40], then replaces that vector with A3',
      lambda a,b:And(byte(b.r[36],b.r[39])==byte(a.r[37],a.r[40]),
                    byte(b.r[37],b.r[40])==0xA3))
prove(0x1F,'1F sets R[38]=R[35]+8 modulo 16',lambda a,b:b.r[38]==a.r[35]+8)
prove(0xDD,'DD sets R[38]=R[0]+1 modulo 16',lambda a,b:b.r[38]==a.r[0]+1)
prove(0xE6,'E6 sets R[38]=S+1 modulo 16',lambda a,b:b.r[38]==a.s+1)
prove(0x85,'85 copies R[35] to R[38]',lambda a,b:b.r[38]==a.r[35])
for ip,selector in [(0x05,9),(0x66,9),(0x25,4),(0xA4,4),(0x2E,6),(0xA6,6)]:
    prove(ip,f'{ip:02X} sets S1={selector}',lambda a,b,n=selector:b.s1==n)
for ip in [0x01,0x02,0x03,0x04,0xBA,0xCC]:
    prove(ip,f'{ip:02X} preserves S1',lambda a,b:b.s1==a.s1)
for ip,n in [(0x6C,8),(0x7C,8)]:
    prove(ip,f'{ip:02X} sets R[38]={n}',lambda a,b,n=n:b.r[38]==n)
for ip,n in [(0xAB,15),(0xAD,0)]:
    prove(ip,f'{ip:02X} sets R[26]={n:X}',lambda a,b,n=n:b.r[26]==n)
for ip,n in [(0x96,0x90),(0xA0,0xD3),(0xA1,0xD3),(0xAB,0x93)]:
    prove(ip,f'{ip:02X} replaces A3 vector with {n:02X}',
          lambda a,b,n=n:byte(b.r[37],b.r[40])==n)
for ip in [0xA2,0xE5,0xE6,0xED,0xEE,0xE9,0xAD]:
    prove(ip,f'{ip:02X} preserves A3 vector',
          lambda a,b:byte(b.r[37],b.r[40])==byte(a.r[37],a.r[40]))
prove(0xF8,'F8 leaves S1 only in {0,1,8,9}, never D',
      lambda a,b:Or(*[b.s1==n for n in [0,1,8,9]]))
prove(0xF9,'F9 preserves S1',lambda a,b:b.s1==a.s1)
prove(0xFC,'FC copies S1 to R[35]',lambda a,b:b.r[35]==a.s1)
prove(0x93,'93 always enters 94 and leaves S=R[40]',
      lambda a,b:And(byte(b.r[36],b.r[39])==0x94,b.s==b.r[40]))
prove(0x94,'94 copies old R[40] and S into the two A3 vector nibbles',
      lambda a,b:And(b.r[37]==a.r[40],b.r[40]==a.s))
prove(0x6D,'6D enters 60 iff R[26] is nonzero',
      lambda a,b:(byte(b.r[36],b.r[39])==0x60)==(a.r[26]!=0))

def path(sequence):
    a=State('path_'+'_'.join(f'{ip:02x}' for ip in sequence));b=a
    p=base(a,sequence[0])
    for step,(ip,nxt) in enumerate(zip(sequence,sequence[1:])):
        b=execute(b,ip,*keys(f'path_keys_{step}'))
        p.add(byte(b.r[36],b.r[39])==nxt)
    return a,b,p

seq=[0x1F,0x1D,0x28,0x7E,0x77,0x6D,0x60,0xC8]
_,_,p=path(seq);assert p.check()==unsat
print('PASS: direct 1F->1D->28->7E->77->6D->60->C8 is impossible')
seq=[0xF8,0xF9,0xFC,0x68,0xA5,0x1F,0x1D,0x25,0x01,0x02,0x03,0x04,
     0xBA,0xCB,0xDD,0xD4,0x26,0x28,0x7E,0x77,0x6D,0x60,0xC8]
_,_,p=path(seq);assert p.check()==unsat
print('PASS: timing detour F8->F9 cannot open the tested register-write route to C8')

for seq,label in [
    ([0xB3,0xB9,0xF8,0xF9,0xFC,0x68,0x95],
     'B3->B9->F8->F9->FC cannot enter 95 through 68'),
    ([0xA5,0x1F,0x12,0xC6,0x38,0x06,0x07,0x6D,0x60,0xC8],
     'return/reset route through 12->C6 cannot enter C8 through 60'),
    ([0xA5,0x1F,0x12,0xC6,0x38,0x06,0x07,0x6D,0x6F,0x62,0x6E,
      0x61,0x3A,0x06,0x07,0x6D,0x60,0xC8],
     'tested reset-path detour through 6F->62->6E->61->3A cannot enter C8')]:
    _,_,p=path(seq);assert p.check()==unsat
    print('PASS:',label)

a,b,p=path([0x93,0x94,0x95])
assert p.check()==sat
p.add(b.r[37]!=b.r[40]);assert p.check()==unsat
print('PASS: 93->94 leaves only diagonal A3 vectors 00,11,...,FF')

a,b,p=path([0x12,0xC6,0x38])
assert p.check()==sat
p.add(b.r[26]!=0);assert p.check()==unsat
print('PASS: 12->C6 leaves R[26]=0')

# A positive witness in the relaxed model prevents silently treating arbitrary
# starting states / ring streams as real keyboard-side reachability.
seq=[0x1F,0x1D,0x25,0x01,0x02,0x03,0x04,0xBA,0xCB,0xDD,0xD4,
     0x26,0x28,0x7E,0x77,0x6D,0x60,0xC8]
a,b,p=path(seq)
p.add(a.r[0]==3,a.r[26]==8,a.r[35]==7,a.s1==13,
      a.r[25]==0,a.r[31]==0)
assert p.check()==sat
print('PASS: artificially prepared register-write route remains SAT; not a calculator protocol')

a=State('exact_6d_60_gate')
b=execute(a,0x6D,*keys('gate6d'))
c=execute(b,0x60,*keys('gate60'))
p=base(a,0x6D)
p.add(And(byte(b.r[36],b.r[39])==0x60,byte(c.r[36],c.r[39])==0xC8)
      !=And(a.r[26]!=0,a.r[25]==a.r[31],a.r[38]==4))
assert p.check()==unsat
print('PASS: 6D->60->C8 iff R[26]!=0, R[25]=R[31], and R[38]=4')

seq=[0x12,0xC6,0x38,0x06,0x07]
a=State('discard_c7');b=a;p=base(a,seq[0])
for lane in range(3):p.add(byte(a.st[36+lane],a.st[39+lane])!=0xC7)
for index,ip in enumerate(seq):
    b=execute(b,ip,*keys(f'discard_keys_{index}'))
    if index+1<len(seq):
        p.push();p.add(byte(b.r[36],b.r[39])!=seq[index+1])
        assert p.check()==unsat, f'unexpected exit from {ip:02X}'
        p.pop()
p.push();p.add(~Or(byte(b.r[36],b.r[39])==0x09,byte(b.r[36],b.r[39])==0x6D))
assert p.check()==unsat
p.pop()
for branch in ([0x09,0x99],[0x09,0x39],[0x6D]):
    c=b;p.push();p.add(byte(c.r[36],c.r[39])==branch[0])
    for index,ip in enumerate(branch):
        c=execute(c,ip,*keys(f'finish_{branch[0]}_{index}'))
        if index+1<len(branch):
            p.push();p.add(~Or(byte(c.r[36],c.r[39])==0x39,
                              byte(c.r[36],c.r[39])==0x99))
            assert p.check()==unsat
            p.pop()
            p.add(byte(c.r[36],c.r[39])==branch[index+1])
    p.add(Or(*[byte(c.st[36+lane],c.st[39+lane])==0xC7 for lane in range(3)]))
    assert p.check()==unsat
    p.pop()
print('PASS: all key-dependent exits after 12->C6 discard C7 before any return')
print(f'PASS: {count} universal one-command facts and 10 path checks')
