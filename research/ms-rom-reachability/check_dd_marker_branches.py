#!/usr/bin/env python3
"""Read-return branches for initial marker0/F, before another DD.

Universal, unbounded loop closure facts use arbitrary chip data and
per-tick keys/ring. The write-helper closure is separately checked by
check_read_write_exit.py. No full C8 unreachability claim is made.
"""
import runpy
from pathlib import Path

from z3 import And, Or, sat, unsat

root = Path(__file__).resolve().parent
m = runpy.run_path(str(root / 'analyze_dd_stack_lifetime.py'))
q = m['model']()
State, execute, base, keys = (q[n] for n in ('State', 'execute', 'base', 'keys'))
address, stack = m['address'], m['stack']
facts = 0


def prove(ip, successors, condition=lambda a: True, extra=lambda a, b: True):
    global facts
    a = State(f'marker_branch_{facts}')
    b = execute(a, ip, *keys(f'marker_branch_keys_{facts}'))
    p = base(a, ip)
    p.add(condition(a))
    assert p.check() == sat, ('vacuous condition', ip)
    p.add(~And(Or(*[address(b) == n for n in successors]),
               *[b.r[n] == a.r[n] for n in (2, 26, 38)], extra(a, b)))
    assert p.check() == unsat, ('branch fact', ip, successors)
    facts += 1
    print(f'PASS: {ip:02X}->'+ '/'.join(f'{n:02X}' for n in successors)
          +' with R2/R26/R38 preserved under the stated condition', flush=True)


prove(0x2F, (0x20, 0x21))
prove(0x20, (0x2F,))
prove(0x21, (0x22, 0x23))
prove(0x22, (0x36,))
prove(0x36, (0x25,), lambda a: a.r[26] == 15)
prove(0x36, (0x37,), lambda a: a.r[26] == 0)
prove(0x37, (0x25, 0x38), lambda a: a.r[26] == 0)
prove(0x38, (0x06,), extra=lambda a, b: And(b.r[27] == 15, b.r[32] == 0))
prove(0x06, (0x07,), extra=lambda a, b: And(b.r[27] == a.r[27], b.r[32] == a.r[32]))
prove(0x23, (0x24, 0x25))
prove(0x24, (0x25,))
prove(0x25, (0x01,), extra=lambda a, b: And(b.s1 == 4,
      *[v == n for v, n in zip(stack(b), [0x26]+stack(a)[:2])]))
for ip, successors in ((1, (1, 2)), (2, (2, 3)), (3, (4,)),
                       (4, (0xBA,)), (0xBA, (0xCB,)), (0xCB, (0xDD,))):
    prove(ip, successors, lambda a: a.s1 == 4,
          lambda a, b: And(b.s1 == 4, *[v == w for v, w in zip(stack(b), stack(a))]))

print(f'PASS: {facts} universal branch/loop facts. From D6/2F, marker F '
      'must wait forever or encounter another DD before any 60. Marker0 '
      'must wait, encounter another DD, or reach 07 through 38/06 with '
      'R27=F/R32=0 and the original R2 and marker0. These statements '
      'hold for any selector, including 4 and 9.', flush=True)
