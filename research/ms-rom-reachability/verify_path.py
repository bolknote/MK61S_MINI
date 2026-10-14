#!/usr/bin/env python3
"""Check an explicit internal ROM path, with exact inter-command data flow."""
import argparse
import runpy
from pathlib import Path
from z3 import ZeroExt, sat, unsat

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('path', help='space-separated internal hexadecimal ROM addresses')
parser.add_argument('--expect', choices=['sat', 'unsat'])
parser.add_argument('--reset', action='store_true', help='start from the emulator zero state; path must begin at 00')
parser.add_argument('--no-keys', action='store_true', help='use released keys instead of arbitrary tick-level signals')
args = parser.parse_args()
sequence = [int(item, 16) for item in args.path.split()]
assert len(sequence) >= 2 and all(0 <= ip <= 255 for ip in sequence)
q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
initial = q['State']('path_initial')
state = initial
solver = q['base_solver'](initial, sequence[0])
if args.reset:
    assert sequence[0] == 0, '--reset requires the initial command 00'
    for group in ('r', 'm', 'st'):
        solver.add(*[value == 0 for value in getattr(initial, group)])
    solver.add(*[getattr(initial, name) == 0 for name in ('s', 's1', 'l', 't', 'carry')])

for index, (ip, next_ip) in enumerate(zip(sequence, sequence[1:])):
    keys = (0, 0) if args.no_keys else q['arbitrary_keys'](f'path_keys_{index}')
    state = q['execute_command'](state, ip, *keys)
    address = ZeroExt(4, state.r[36]) | (ZeroExt(4, state.r[39]) << 4)
    solver.assert_and_track(address == next_ip, f'step_{index}_{ip:02X}_{next_ip:02X}')
outcome = solver.check()
assert outcome in (sat, unsat), solver.reason_unknown()
print(outcome)
if outcome == unsat:
    print('Unsatisfiable transition core:', solver.unsat_core())
else:
    print('Nonzero initial fields:', ' '.join(q['nonzero_model_values'](solver.model(), initial)))
    print('SAT only in the relaxed model: ring inputs are arbitrary. This is not a physical protocol.')
if args.expect:
    assert str(outcome) == args.expect
