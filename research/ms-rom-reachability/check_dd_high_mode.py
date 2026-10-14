#!/usr/bin/env python3
"""Positive controls for the exact-stack DD result and the preceding read.

These paths start from artificial chip states and arbitrary serial inputs.
They do not establish a key sequence, reset reachability, or a full K1/K2.
The universal read-body facts include all repetitions of 01/02.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ULT, sat, unsat

m = runpy.run_path(str(Path(__file__).with_name('analyze_dd_stack_lifetime.py')))
q = m['model']()
State, execute, base, keys = (q[n] for n in ('State', 'execute', 'base', 'keys'))
address, stack, byte = (m[n] for n in ('address', 'stack', 'byte'))

facts = 0


def prove(ip, label, claim, condition=None):
    global facts
    a = State(f'high_read_fact_{facts}')
    b = execute(a, ip, *keys(f'high_read_keys_{facts}'))
    p = base(a, ip)
    if condition is not None:
        p.add(condition(a))
    assert p.check() == sat, ('vacuous fact', label)
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    facts += 1
    print('PASS:', label, flush=True)


prove(0x2E, '2E enters 01 with S1=6/vector FF, pushes 2F, preserves R2/R26',
      lambda a, b: And(address(b) == 1, b.s1 == 6,
          byte(b.r[37], b.r[40]) == 0xFF,
          b.r[2] == a.r[2], b.r[26] == a.r[26],
          *[v == w for v, w in zip(stack(b), [0x2F]+stack(a)[:2])]))
for ip, successors in [(1, (1, 2)), (2, (2, 3)), (3, (4,)), (4, (0xBA,)),
                       (0xBA, (0xCB,)), (0xCB, (0xDD,))]:
    prove(ip, f'{ip:02X}: the read body preserves R2/R26/S1/vector/whole stack',
          lambda a, b, successors=successors: And(
              Or(*[address(b) == nxt for nxt in successors]),
              b.r[2] == a.r[2], b.r[26] == a.r[26], b.s1 == a.s1,
              b.r[37] == a.r[37], b.r[40] == a.r[40],
              *[v == w for v, w in zip(stack(a), stack(b))]),
          lambda a: a.s1 == 6)


SUFFIX = [int(v, 16) for v in 'DD D6 2F 21 22 36 27 38 06 07 6D 60 C8'.split()]
PREFIX = [0x2E, 1, 2, 3, 4, 0xBA, 0xCB]


def build(sequence, label, initial):
    a = State(label)
    p = base(a, sequence[0])
    p.add(initial(a))
    states = [a]
    b = a
    for index, (ip, nxt) in enumerate(zip(sequence, sequence[1:])):
        b = execute(b, ip, *keys(f'{label}_keys_{index}'))
        p.add(address(b) == nxt)
        states.append(b)
    return a, b, p, states


# This stack and marker are admitted by the independently completed reset
# projection. Combining them with a high R2 is NOT asserted reachable.
initial = lambda a: And(a.s1 == 6, a.r[0] == 3,
    byte(a.r[37], a.r[40]) == 0xFF, Or(a.r[41] == 0, a.r[41] == 15),
    *[v == w for v, w in zip(stack(a), (0x2F, 0x6E, 0x08))])
a, b, p, _ = build(SUFFIX, 'high_dd_control', initial)
assert p.check() == sat
p.push()
p.add(~And(UGE(a.r[2], 5), a.r[26] == 1, ULT(a.r[29], 5)))
assert p.check() == unsat
p.pop()
for value in range(5, 16):
    p.push()
    p.add(a.r[2] == value)
    assert p.check() == sat, ('missing high-mode positive control', value)
    p.pop()
print('PASS: exact DD suffix is SAT for all R2=5..F; it requires R26=1 '
      'and R29<5. These are necessary conditions, not a sufficient recipe.', flush=True)
p.add(ULT(a.r[2], 5))
assert p.check() == unsat
print('PASS: low R2 excludes the same exact suffix, with arbitrary tick-level keys.', flush=True)

# Start one complete read earlier. The helper constructs the correct vector
# and return tag itself; only its older stack bytes and the artificial mode
# are constrained at entry. R0=3 is required at the later DD, not injected.
a, b, p, states = build(PREFIX+SUFFIX, 'high_2e_control',
    lambda a: And(a.r[2] == 8, a.r[26] == 1,
        Or(a.r[41] == 0, a.r[41] == 15),
        stack(a)[0] == 0x6E, stack(a)[1] == 0x08))
dd = states[len(PREFIX)]
p.add(dd.r[0] == 3)
assert p.check() == sat
p.push()
p.add(~And(dd.r[2] == 8, dd.r[26] == 1, dd.s1 == 6,
           byte(dd.r[37], dd.r[40]) == 0xFF,
           *[v == w for v, w in zip(stack(dd), (0x2F, 0x6E, 0x08))]))
assert p.check() == unsat
p.pop()
print('PASS: exact 2E read + DD suffix is SAT with an artificial high-mode '
      'input; the read preserves the discriminator rather than creating it.', flush=True)
print(f'PASS: {facts} universal read facts and positive/negative exact-path '
      'controls. No calculator-side protocol has been found.', flush=True)
