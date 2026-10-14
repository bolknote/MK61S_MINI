#!/usr/bin/env python3
"""Close DD return families without assuming a low R2 or a zero marker.

The context inventory is independently derived by analyze_dd_contexts.py.
The DC continuation is closed by analyze_1f_lifetime.py --entry at-dc.
This file proves the exact connecting fragments, including the second byte
of a live return stack after a return to 93. Arbitrary tick-level keys/ring.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)


def address(a):
    return byte(a.r[36], a.r[39])


def stack(a):
    return [byte(a.st[36+i], a.st[39+i]) for i in range(3)]


count = 0


def prove(ip, label, claim):
    global count
    a = State(f'dd_suffix_{ip}')
    b = execute(a, ip, *keys(f'dd_suffix_keys_{ip}'))
    p = base(a, ip)
    assert p.check() == sat
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    count += 1
    print('PASS:', label, flush=True)


for ip in (0xD4, 0xD6):
    prove(ip, f'{ip:02X} returns through the exact top byte and rotates the whole stack',
          lambda a, b: And(address(b) == stack(a)[0], b.r[38] == a.r[38],
                           *[x == y for x, y in zip(stack(b), stack(a)[1:]+stack(a)[:1])]))
for ip, successors in [(0x76, (0xE2,)), (0xE2, (0xE5,)), (0xE5, (0xE5, 0xE6)),
                       (0xA5, (0x1F,)), (0xA7, (0xE5,)), (0xAF, (0xAE,)),
                       (0xAE, (0xDC,)), (0xC3, (0xC2,)), (0xC2, (0xDC,)),
                       (0xCF, (0xC2, 0xC3))]:
    prove(ip, f'{ip:02X} stays on its overwrite/DC route with R38 unchanged',
          lambda a, b, successors=successors: And(b.r[38] == a.r[38],
              Or(*[address(b) == nxt for nxt in successors])))

# A restoration at 93 can change R2 again. Nevertheless its control sequence
# is unconditional and consumes the NEXT live return byte, not an arbitrary
# address. Prove every edge as a consequence; do not assume the desired path.
for return_ip in (0xD4, 0xD6):
    a = State(f'dd_return93_{return_ip}')
    p = base(a, return_ip)
    p.add(stack(a)[0] == 0x93)
    assert p.check() == sat
    b = a
    sequence = [return_ip, 0x93, 0x94, 0x95, 0x98, 0x9A]
    for index, ip in enumerate(sequence):
        b = execute(b, ip, *keys(f'dd_return93_keys_{return_ip}_{index}'))
        expected = sequence[index+1] if index+1 < len(sequence) else stack(a)[1]
        p.push()
        p.add(~And(address(b) == expected, b.r[38] == a.r[38]))
        assert p.check() == unsat, (return_ip, ip, 'not a forced continuation')
        p.pop()
    print(f'PASS: {return_ip:02X}->93->94->95->98->9A is forced, returns through '
          'the original second stack byte, and preserves R38', flush=True)
print(f'PASS: {count} one-command facts and two forced restoration chains. '
      'For contexts with top 93 and second DD/E5, restoring R2 cannot reach '
      '07 before another selector assignment. AF/C3/CF connect to the '
      'separately closed DC family.', flush=True)
