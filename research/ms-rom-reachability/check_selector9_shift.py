#!/usr/bin/env python3
"""The three-increment selector-9 bootstrap from 07 loses the needed digit.

This closes one preparation family, not every possible path to C8. Proofs
allow arbitrary keys/ring. The invariant at 07 additionally uses the complete
source coverage and the previously proved 05/tag06 read-return protocol.
"""
import runpy
from pathlib import Path

from z3 import And, BitVec, BitVecVal, If, Or, Solver, UGE, ULT, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys = (q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
byte = lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address = lambda a:byte(a.r[36],a.r[39])
facts = 0


def prove(ip,label,claim):
    global facts
    a = State(f'nine_shift_fact_{facts}')
    b = execute(a,ip,*keys(f'nine_shift_fact_keys_{facts}'))
    p = base(a,ip)
    assert p.check()==sat
    p.add(~claim(a,b))
    assert p.check()==unsat,label
    facts += 1
    print('PASS:',label,flush=True)


for ip in (0x38,0x3A,0x55):
    prove(ip,f'{ip:02X} enters 06 and fills R27 with F',
          lambda a,b:And(address(b)==0x06,b.r[27]==15))
prove(0x06,'06 enters 07, preserves R27, and leaves a decimal low counter digit',
      lambda a,b:And(address(b)==0x07,b.r[27]==a.r[27],ULT(b.r[31],10)))
for ip in (0x01,0x02,0x03,0x04,0xBA,0xCB):
    prove(ip,f'{ip:02X} preserves R0 during the read',lambda a,b:b.r[0]==a.r[0])
prove(0xDD,'DD sets selector to old R0+1 modulo 16',lambda a,b:b.r[38]==a.r[0]+1)
print('PASS: together with selector9 source coverage and the 05/tag06 '
      'protocol (which returns with selector8), every selector9/07 has '
      'R27=F before the first C8.',flush=True)

# The input 07 came through 06, whose output low digit is always decimal.
# The 6F/62 pair aligns R25 with that digit; 6E subtracts three. Prove that
# extra passes cannot be chosen freely while keeping selector9.
lo,hi = BitVec('nine_counter_lo',4),BitVec('nine_counter_hi',4)
low = If(ULT(lo,3),lo+7,lo-3)
high = hi-If(ULT(lo,3),BitVecVal(1,4),BitVecVal(0,4))
guards = []
for n in range(1,4):
    guards.append(UGE(high,12))
    carry = If(ULT(low,9),BitVecVal(0,4),BitVecVal(1,4))
    low,high = If(ULT(low,9),low+1,low+7),high+carry
    p = Solver()
    p.add(ULT(lo,10),low==lo if n<3 else low!=lo)
    assert p.check()==unsat,('first equality after subtract-three',n)
p = Solver()
p.add(ULT(lo,10),And(*guards))
actual = set(q['possible_values'](byte(lo,hi),p,257))
expected = {0}|set(range(0xC3,0xCA))|{16*h+l for h in (13,14,15) for l in range(10)}
assert actual==expected,(actual,expected)
print('PASS: after subtract-three, a decimal low digit first matches at '
      'the third increment. All three high-counter guards survive exactly '
      'for 38 counters: 00, C3..C9, D0..D9, E0..E9, F0..F9. '
      'At that match selector9 forces 18, so adding ten extra passes cannot '
      'delay the read. A failed guard takes the selector-overwriting 63 path.',flush=True)


def addresses(text):
    return [int(n,16) for n in text.split()]


PREFIX = addresses('07 6D 6F 62 6E 61') + \
    addresses('3A 06 07 6D 60 61')*2 + \
    addresses('3A 06 07 6D 60 18 1B 1D 2E 01 02 02 02 03 04 BA CB DD')
TAIL = addresses('D6 2F 21 22 36 27 38 06 07 6D 60') + \
    addresses('61 3A 06 07 6D 60')*9 + [0xC8]


def build(sequence,label,r27=None):
    a = State(label)
    p = base(a,sequence[0])
    p.add(a.r[38]==9,a.r[26]==0,UGE(a.r[2],5))
    if r27 is not None:
        p.add(a.r[27]==r27)
    b = a
    for i,(ip,nxt) in enumerate(zip(sequence,sequence[1:])):
        b = execute(b,ip,*keys(f'{label}_keys_{i}'))
        p.add(address(b)==nxt)
    return a,b,p


a,b,p = build(PREFIX,'nine_07_provenance')
assert p.check()==sat
p.add(b.r[0]!=a.r[27])
assert p.check()==unsat
print('PASS: the three-increment preparation from 07 feeds its initial '
      'R27 into the subsequent DD R0, for arbitrary initial data/keys/ring.',flush=True)

a,b,p = build(PREFIX,'nine_07_real_digit',15)
assert p.check()==sat
p.add(b.r[0]!=15)
assert p.check()==unsat
a,b,p = build(PREFIX+TAIL,'nine_07_real_digit_tail',15)
assert p.check()==unsat
print('PASS: with the proved R27=F, the read prefix is nonempty but DD '
      'sets selector0, never4. The tested C8 continuation is UNSAT.',flush=True)
a,b,p = build(PREFIX+TAIL,'nine_07_artificial_digit_tail',3)
assert p.check()==sat
print('PASS: the same C8 chain with artificial initial R27=3 is SAT. '
      'Its failure with F is a data-flow conflict, not an empty path template.',flush=True)

# A concrete candidate raised while looking for a real source of selector9:
# start at an earlier DD in the R26=0/type5 family. The immediate 38->06
# supplies the F before entering the preparation just proved above.
first = addresses('DD D6 2F 21 22 36 37 38 06')
seq = first+PREFIX+TAIL
a = State('nine_two_dd')
p = base(a,0xDD)
p.add(a.r[0]==8,a.s1==6,a.r[26]==0,a.r[35]==5,
      byte(a.r[37],a.r[40])==0xFF,
      *[byte(a.st[36+i],a.st[39+i])==n for i,n in enumerate((0x2F,0xAC,0x9A))])
b = a
for i,(ip,nxt) in enumerate(zip(seq,seq[1:])):
    b = execute(b,ip,*keys(f'nine_two_dd_keys_{i}'))
    p.add(address(b)==nxt)
    if nxt==0x60 and seq[i+2]==0x18:
        p.push()
        p.add(b.r[26]==1,b.r[38]==9,UGE(b.r[2],5),b.r[25]==b.r[31])
        assert p.check()==sat, 'nonempty DD9 high-mode bootstrap control'
        for value in range(5,16):
            p.push()
            p.add(a.r[2]==value)
            assert p.check()==sat, ('missing high-mode DD9 control',value)
            p.pop()
        p.pop()
        p.push()
        p.add(ULT(a.r[2],5))
        assert p.check()==unsat, 'low-mode boundary of the exact DD9 path'
        p.pop()
        print('PASS: DD9->D6/2F/AC/9A reaches the selected 60 bootstrap '
              'from an artificial initial state for every R2=5..F, but '
              'never for R2<5. This is a positive boundary control, '
              'not a reset-reachable seed.',flush=True)
    if nxt==0xDD:
        assert p.check()==sat, 'prefix through the second DD must be nonempty'
        p.push()
        p.add(b.r[0]!=15)
        assert p.check()==unsat, 'second DD must receive the fill digit F'
        p.pop()
        print('PASS: the same positive DD9 prefix forces R0=F at its '
              'following DD; a high-mode bootstrap alone cannot give '
              'the selector4 required by this C8 continuation.',flush=True)
assert p.check()==unsat
print('PASS: the 110-transition two-DD candidate with the admitted '
      '2F/AC/9A return context is also UNSAT for the same fill-digit reason.',flush=True)
print(f'PASS: {facts} local facts, provenance identity, and positive/negative '
      'exact paths. Other preparation routes remain unproved.',flush=True)
