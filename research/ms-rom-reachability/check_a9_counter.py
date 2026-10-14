#!/usr/bin/env python3
"""Exact counter/vector correlation for the AD->A9->93 restoration route.

This is a bounded architectural lemma, not a claim that every A3->77 must
take this route. Arbitrary initial data, tick-level keys and ring inputs are
allowed. Expected edges are proved forced, not imposed as path constraints.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))


def byte(lo,hi):
    return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)


def address(a):
    return byte(a.r[36],a.r[39])


def vector(a):
    return byte(a.r[37],a.r[40])


def stack(a):
    return [byte(a.st[36+i],a.st[39+i]) for i in range(3)]


def prove(p,claim,label):
    assert p.check() == sat, f'empty assumptions: {label}'
    p.push();p.add(~claim)
    assert p.check() == unsat,label
    p.pop()
    print('PASS:',label,flush=True)


a = State('a9_source')
b = execute(a,0xAD,*keys('a9_source_keys'))
p = base(a,0xAD)
prove(p,Or(address(b) != 0xA9,And(b.r[32] == 9,b.s1 == 9,b.r[26] == 0)),
      'AD->A9 establishes R32=9, S1=9, R26=0')

a = State('a9_restore');p = base(a,0xA9)
p.add(stack(a)[0] == 0x93,a.r[32] == 9,a.s1 == 9)
b = a
sequence = [0xA9,0x93,0x94,0x95,0x98,0x9A]
for index,ip in enumerate(sequence):
    b = execute(b,ip,*keys(f'a9_restore_keys_{index}'))
    nxt = sequence[index+1] if index+1 < len(sequence) else stack(a)[1]
    prove(p,address(b) == nxt,f'A9 restoration edge {ip:02X} is forced')
prove(p,And(vector(b) == byte(a.r[35],a.r[35]),
            b.r[31] == 9,b.r[34] == a.r[35],b.r[38] == a.r[38]),
      'A9->93..9A returns with diagonal vector vv and counter v9, v=old R35')
prove(p,Or(vector(b) != 0x77,And(b.r[31] == 9,b.r[34] == 7)),
      'vector 77 and an arbitrary counter cannot be selected independently on this route')

# These helpers may wait but cannot change the counter/vector correlation.
for ip in (0xE5,0xE6,0xE9,0xAD,0xA2,0xA3,0x77,0x6D):
    a = State(f'a9_preserve_{ip}');b = execute(a,ip,*keys(f'a9_preserve_keys_{ip}'))
    prove(base(a,ip),And(b.r[31] == a.r[31],b.r[34] == a.r[34]),
          f'{ip:02X} preserves the counter, including any waiting repetitions')

a = State('a9_detour');p = base(a,0x77)
p.add(a.r[26] == 0,a.r[31] == 9,a.r[34] == 7)
b = a
sequence = [0x77,0x6D,0x6F,0x62,0x6E,0x61]
for index,ip in enumerate(sequence):
    b = execute(b,ip,*keys(f'a9_detour_keys_{index}'))
    nxt = sequence[index+1] if index+1 < len(sequence) else 0x63
    prove(p,address(b) == nxt,f'counter-79 detour edge {ip:02X}->{nxt:02X} is forced')
prove(p,And(b.r[31] == 6,b.r[34] == 7),
      'the counter becomes 76; the detour must enter 63, never 3A')
print('PASS: AD->A9/top-93 restoration lemma and its forced counter detour. '
      'This does not classify all possible first sources of a diagonal A3 vector.',flush=True)
