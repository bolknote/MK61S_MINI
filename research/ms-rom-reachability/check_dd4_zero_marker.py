#!/usr/bin/env python3
"""A direct high-mode DD4/marker0 route to C8, without selector9 preparation.

All positive checks use an artificial initial chip state and arbitrary ring.
The stack/marker are admitted by reset projection; their combination with
high R2 is NOT asserted keyboard-reachable.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ULT, sat, unsat

m = runpy.run_path(str(Path(__file__).with_name('analyze_dd_stack_lifetime.py')))
q = m['model']()
address = m['address']
seq = [int(s, 16) for s in (
    'DD D6 2F 21 22 36 37 38 06 07 6D 6F 62 6E 61 '
    '3A 06 07 6D 60 61 3A 06 07 6D 60 61 3A 06 07 6D 60 C8').split()]
a = q['State']('dd4_zero_marker')
p = m['seed_solver'](a, (0x2F, 0xAC, 0x9A), 'all')
p.add(a.r[26] == 0, a.r[35] == 5)
# Further necessary fields proved by check_dd0_cycle_sources.py: the cycle
# dispatcher assigned D before this DD, and its read index is one of 0..3.
p.add(a.r[38] == 13, Or(*[a.r[32] == n for n in range(4)]))
b, states = a, [a]
for i, (ip, nxt) in enumerate(zip(seq, seq[1:])):
    b = q['execute'](b, ip, *q['keys'](f'dd4_zero_marker_keys_{i}'))
    p.add(address(b) == nxt)
    states.append(b)
assert p.check() == sat, 'nonempty direct DD4/marker0 positive control'
for value in range(5, 16):
    p.push()
    p.add(a.r[2] == value)
    assert p.check() == sat, ('missing high-mode control', value)
    p.pop()
p.push()
p.add(ULT(a.r[2], 5))
assert p.check() == unsat, 'low-mode exclusion for this exact route'
p.pop()
p.push()
p.add(~And(b.r[38] == 4, b.r[25] == b.r[31], b.r[26] != 0,
           UGE(b.r[2], 5)))
assert p.check() == unsat, 'C8 gate conditions'
p.pop()
ready = states[seq.index(0x62)+1]
possible = sorted(q['domain'](p, ready.r[26]))
print(f'PASS: exact {len(seq)-1}-transition DD4/marker0 route to C8 is SAT '
      'for every initial R2=5..F, but UNSAT for R2<5.', flush=True)
print('Marker values after 62 on this route:', ','.join(f'{n:X}' for n in possible), flush=True)
assert possible == list(range(1, 16)), 'control deliberately allows nonzero markers other than 1'
indices = sorted(q['domain'](p, a.r[32]))
assert indices == list(range(4)), 'all four cycle read indices remain locally compatible'
print('PASS: the cycle-derived incoming selectorD and each read index 0..3 '
      'are compatible with this direct path; native preparation remains unproved.', flush=True)
# The route requires no selector9: the initial DD assigns 4 and every
# following command up to the C8 input preserves it.
for i, state in enumerate(states[1:], start=1):
    p.push()
    p.add(state.r[38] != 4)
    assert p.check() == unsat, ('selector lost on direct route', i)
    p.pop()
print('PASS: selector4 is preserved throughout. The fill digit F that '
      'spoils the later read in the selector9 route does not block this '
      'direct C8 entry, which performs no intervening DD. No keyboard '
      'preparation of the high-mode seed has been found.', flush=True)
