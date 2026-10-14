#!/usr/bin/env python3
"""Parametric A8 exit/reentry conditions, separate from keyboard reachability.

All payloads, serial ring inputs and per-tick keyboard signals are arbitrary.
Positive parameter choices below are NOT asserted reachable from reset.
"""
from pathlib import Path
import runpy
from z3 import And, BitVecVal, If, UGE, ULT, ZeroExt, sat, unsat


def check(q):
    byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
    address=lambda a:byte(a.r[36],a.r[39])
    head=[0x60]+[0xA8]*8+[0xA9,0x6E,0x61]
    scan=[0x3A,0x06,0x07,0x6D,0x60,0x61]
    results={}

    def path(label,sequence,condition):
        a=q['State']('a8_exit_'+label);p=q['base_solver'](a,0x60)
        p.add(a.r[38]==2,a.r[25]==a.r[31],
              byte(a.st[36],a.st[39])==0x6E,condition(a))
        assert p.check()==sat,label
        b=a
        for index,(ip,nxt) in enumerate(zip(sequence,sequence[1:])):
            b=q['execute_command'](b,ip,*q['arbitrary_keys'](f'{label}_keys_{index}'))
            p.push();p.add(address(b)!=nxt);outcome=p.check();p.pop()
            assert outcome==unsat,(label,index,f'{ip:02X}->{nxt:02X}',outcome)
        return a,b,p

    a,b,p=path('general',head,lambda a:True)
    c=q['execute_command'](b,0x61,*q['arbitrary_keys']('a8_exit_decision'))
    decremented_low=If(ULT(a.r[31],3),a.r[31]+7,a.r[31]-3)
    decremented_high=a.r[34]-If(ULT(a.r[31],3),q['N4'](1),q['N4'](0))
    expected=If(ULT(decremented_high,12),BitVecVal(0x63,8),BitVecVal(0x3A,8))
    p.push();p.add(~And(b.r[31]==decremented_low,b.r[34]==decremented_high,address(c)==expected))
    assert p.check()==unsat;p.pop()
    print('PASS: first exit is 63 iff (old PC high - [old PC low < 3]) mod 16 < 12.',flush=True)

    for digit in (1,2):
        # With PC=01 or 02 the scan crosses 00 before it can return to the
        # target digit. The following 61 therefore leaves for 63.
        sequence=head+scan*(3-digit)+[0x63]
        a,b,p=path(f'one_pass_{digit}',sequence,lambda a,digit=digit:
                   And(a.r[31]==digit,a.r[34]==0,UGE(a.r[2],5),a.r[26]!=0))
        results[digit]=sequence
        print(f'PASS: PC=0{digit}, comparison={digit}: exactly eight A8 swaps, '
              f'then 63 after {len(sequence)-1} commands; no second A8.',flush=True)

    # The zero-counter loop holds for an entire parameterized controller
    # class, not just the single full native snapshot used in the first proof.
    sequence=head+scan*2+scan[:-1]
    a,b,p=path('zero_loop',sequence,lambda a:
               And(a.r[31]==0,a.r[34]==0,UGE(a.r[2],5),a.r[26]!=0))
    claims=[b.r[31]==0,b.r[34]==0,b.r[25]==0,b.r[38]==2,
            b.r[2]==a.r[2],b.r[26]==a.r[26],
            byte(b.st[36],b.st[39])==0x6E]
    p.add(~And(*claims));assert p.check()==unsat
    print('PASS: PC=00, comparison=0, mode>=5, marker!=0 is an inductive 28-command loop.',flush=True)
    return results


if __name__=='__main__':
    check(runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py'))))
