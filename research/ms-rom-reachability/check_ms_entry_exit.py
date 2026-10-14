#!/usr/bin/env python3
"""Different C7/C8 primitives and the exits of the first 60->C8 entry.

Does not assume the pre-entry A3 vector invariant AFTER C8: C8 explicitly
loads that vector from the M2 page. Entry through 07/77 fixes the immediate
return to 6E, however, and the later 61 overwrites the freshly loaded vector.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def byte(lo,hi):
    return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)


def address(a):
    return byte(a.r[36],a.r[39])


def vector(a):
    return byte(a.r[37],a.r[40])


for ip in (0xC7,0xC8):
    a = State(f'ms_body_{ip}')
    b = execute(a,ip,*keys(f'ms_body_keys_{ip}'))
    p = base(a,ip)
    p.add(~And(address(b) == byte(a.st[36],a.st[39]),
                b.r[38] == a.r[38]))
    assert p.check() == unsat
    p = base(a,ip)
    if ip == 0xC7:
        p.add(~And(*[b.r[3*i] == a.m[3*i+1] for i in range(12)],
                   vector(b) == vector(a)))
    else:
        p.add(~And(*[b.r[3*i+1] == a.m[3*i+1] for i in range(14)]))
    assert p.check() == unsat
print('PASS: C7 loads 12 numeric nibbles into internal R1 and preserves the A3 vector; '
      'C8 loads all 14 M2 nibbles into internal R2, including R37/R40. '
      'Both return via the old top address-stack byte and preserve R38.',flush=True)

for origin in (0x07,0x77):
    a = State(f'ms_first_{origin}');b = a;p = base(a,origin)
    sequence = [origin,0x6D,0x60,0xC8]
    for i,(ip,target) in enumerate(zip(sequence,sequence[1:])):
        b = execute(b,ip,*keys(f'ms_first_{origin}_keys_{i}'))
        p.add(address(b) == target)
    assert p.check() == sat
    before_c8 = b
    b = execute(b,0xC8,*keys(f'ms_first_{origin}_c8'))
    p.push()
    p.add(~And(address(b) == 0x6E,
                vector(b) == byte(before_c8.m[37],before_c8.m[40])))
    assert p.check() == unsat
    p.pop()
    after_c8 = b
    b = execute(b,0x6E,*keys(f'ms_first_{origin}_6e'))
    p.push();p.add(~And(address(b) == 0x61,vector(b) == vector(after_c8)))
    assert p.check() == unsat
    p.pop()
    b = execute(b,0x61,*keys(f'ms_first_{origin}_61'))
    p.push();p.add(~And(Or(address(b) == 0x3A,address(b) == 0x63),vector(b) == 0x28))
    assert p.check() == unsat
    p.pop()
    print(f'PASS: {origin:02X}->6D->60->C8 returns to 6E; '
          '6E->61 preserves the loaded A3 vector, then 61 sets it to 28 '
          'and enters 3A or 63. No direct use of the loaded vector by A3.',flush=True)

# A logical gadget chain exists in an artificially prepared state. Its
# return byte A3 cannot be created by the zero-reset address-stack machinery
# (check_type_entry.py). This test explicitly does NOT prove reachability.
a = State('ms_artificial_gadget');p = base(a,0xC8)
b = execute(a,0xC8,*keys('ms_artificial_gadget_c8'))
p.add(address(b) == 0xA3)
b = execute(b,0xA3,*keys('ms_artificial_gadget_a3'))
p.add(address(b) == 0xC7)
assert p.check() == sat
p.add(~And(byte(a.st[36],a.st[39]) == 0xA3,byte(a.m[37],a.m[40]) == 0xC7))
assert p.check() == unsat
print('PASS: artificial C8->A3->C7 is SAT, but requires an already-prepared '
      'return byte A3 and M2 vector C7. It is incompatible with the first-entry '
      '6E return and is not a keyboard protocol.',flush=True)
