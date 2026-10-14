#!/usr/bin/env python3
"""Project real selector9 returns to 62 from the completed reset cover.

The source analysis does not track R2. Positive high-mode projections
therefore remain candidates, not evidence of a native path.
"""
import runpy
import sys
from pathlib import Path

from z3 import And, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
sys.argv = ['analyze_gates.py', '--target', 'cd', '--r38', '--first-entry-lemmas']
m = runpy.run_path(str(root / 'analyze_gates.py'))
assert not m['queue'] and m['terminal'] is None


def solver(state):
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    a, addr, av, old = m['templates'][ip][:4]
    p = m['state_solver'](a, ip)
    if vector == 'diagonal':
        p.add(a.r[37] == a.r[40])
    elif vector is not None:
        p.add(av == vector)
    p.add(Or(*[a.s1 == n for n in selector]), Or(*[a.r[38] == n for n in r38]),
          Or(*[a.r[26] == n for n in r26]), *[v == n for v, n in zip(old, sp)])
    if delta is not None:
        p.add(a.s1-a.r[35] == delta)
    if dr38 is not None:
        p.add(a.r[38]-a.r[35] == dr38)
    return a, p


def values(p, expr):
    p.push()
    result = sorted(m['q']['possible_values'](expr, p, 2**expr.size()+1))
    p.pop()
    return result


rows, executions = [], {}
for state in m['parents']:
    ip, sp = state[:2]
    t = m['templates'][ip]
    if t[4] != 'rotate' or sp[0] != 0x62:
        continue
    a, p = solver(state)
    p.add(t[1] == 0x62, t[11] == 9)
    outcome = p.check()
    assert outcome in (sat, unsat)
    if outcome == unsat:
        continue
    if ip not in executions:
        executions[ip] = m['execute'](a, ip, *m['keys'](f'return62_extra_{ip}'))
    b = executions[ip]
    row = {'source': f'{ip:02X}', 'old_stack': '/'.join(f'{n:02X}' for n in sp),
           'vector': state[2], 'R26_in': values(p, a.r[26]),
           'R2_in': values(p, a.r[2]), 'R2_out': values(p, b.r[2]),
           'R26_out': values(p, b.r[26]), 'S1_out': values(p, b.s1)}
    rows.append(row)
    print(row, flush=True)
print(f'{len(rows)} completed-cover incoming return contexts for selector9/62.', flush=True)
assert not rows, 'a selector9 return62 has not been excluded'
print('PASS: no stack-return edge enters 62 with selector9 before first C7/C8, '
      'for any R2. Together with complete non-return source coverage, '
      'a selector9/62 must come from 6F, despite the genuine tag created by 61.', flush=True)
