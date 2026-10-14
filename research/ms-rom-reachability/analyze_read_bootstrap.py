#!/usr/bin/env python3
"""Project the R26=1 read bootstrap from a completed first-entry fixpoint.

R2 is not tracked by the source abstraction. Its reachability must not be
inferred from the projection. This does not claim a calculator protocol.
"""
import argparse
import runpy
import sys
from pathlib import Path

from z3 import Or, sat, unsat

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verbose', action='store_true')
parser.add_argument('--check-invariants', action='store_true')
args = parser.parse_args()
sys.argv = ['analyze_gates.py', '--target', 'cd', '--r38', '--first-entry-lemmas']
m = runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
assert not m['queue'] and m['terminal'] is None, 'complete reset cover required'

targets = (0x1A, 0x18, 0x1B, 0x1F, 0x1C, 0x1D, 0x2B, 0x2C, 0x2D,
           0x2E, 0x36, 0x60, 0x62, 0x6F)
projection = {ip: [] for ip in targets}
for state in m['parents']:
    ip, sp, vector, selector, delta, r38, dr38, r26, types = state
    if ip not in projection or 1 not in r26:
        continue
    a, addr, av, old = m['templates'][ip][:4]
    p = m['state_solver'](a, ip)
    if vector == 'diagonal':
        p.add(a.r[37] == a.r[40])
    elif vector is not None:
        p.add(av == vector)
    p.add(a.r[26] == 1,
          Or(*[a.s1 == n for n in selector]),
          Or(*[a.r[38] == n for n in r38]),
          *[v == n for v, n in zip(old, sp)])
    if delta is not None:
        p.add(a.s1-a.r[35] == delta)
    if dr38 is not None:
        p.add(a.r[38]-a.r[35] == dr38)
    result = p.check()
    assert result in (sat, unsat)
    if result == unsat:
        continue
    record = {'sp': sp, 'vector': vector}
    for name, expr in [('R38', a.r[38]), ('S1', a.s1), ('R35', a.r[35])]:
        p.push()
        record[name] = tuple(sorted(m['q']['possible_values'](expr, p, 17)))
        p.pop()
    projection[ip].append(record)

if args.check_invariants:
    for ip in (0x1A, 0x1C, 0x2B, 0x2C, 0x2D):
        assert not projection[ip], ('R26=1 must be absent', ip)
    assert projection[0x1F]
    assert all(row['S1'] == (4,) for row in projection[0x1F])
    for ip in (0x18, 0x1B, 0x1D):
        assert projection[ip], ('nonvacuous R26=1 bootstrap required', ip)
        assert all(row['R38'] == (9,) and row['S1'] == (0,)
                   for row in projection[ip]), ip
    assert projection[0x2E]
    assert all(row['R38'] == (9,) and row['S1'] == (14,)
               for row in projection[0x2E])
    print('PASS: complete reset cover excludes R26=1 at 1A/1C/2B/2C/2D; '
          '1F with R26=1 has only S1=4; 18/1B/1D require R38=9 and S1=0; '
          '2E requires R38=9 and S1=E. No restriction on R2 was used.', flush=True)

for ip, rows in projection.items():
    print(f'{ip:02X}, R26=1: {len(rows)} abstract contexts; '+', '.join(
        name+'='+','.join(f'{v:X}' for v in sorted({n for row in rows for n in row[name]}))
        for name in ('R38', 'S1', 'R35')), flush=True)
    stacks = {row['sp'] for row in rows}
    print('  stacks:', ' '.join('/'.join(f'{v:02X}' for v in sp)
                                for sp in sorted(stacks)), flush=True)
    if args.verbose:
        for row in rows:
            print(' ', row, flush=True)
print('Projection only: neither R2 nor numeric counter correlations were '
      'tracked. Any positive context still requires an exact path and '
      'physical preparation.', flush=True)
