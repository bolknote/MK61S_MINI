#!/usr/bin/env python3
"""Exact field compositions; these are local facts, not reachable key paths."""
from z3 import And, Solver, unsat
from ik1302_symbolic import State, execute_command, arbitrary_keys

transport = [0x8C,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
             0x93,0x94,0x95,0x98,0x9A,0x8D]
positions = (0,3,9,12,18,21)


def compose(initial, sequence, prefix):
    state = initial
    for index, ip in enumerate(sequence):
        state = execute_command(state, ip, *arbitrary_keys(f'{prefix}_{index}'))
    return state


def prove(claim, label):
    solver = Solver()
    solver.add(~claim)
    assert solver.check() == unsat, label
    print('PASS:', label, flush=True)


a = State('restore')
b = compose(a, transport, 'restore_keys')
prove(And(*[b.r[n] == a.r[n] for n in positions]),
      '8C/double-restore/8D returns all six opaque raw cache tetras')
prove(And(*[b.r[n] == a.st[n] for n in range(30,36)]),
      '8C/double-restore/8D final R30..35 = initial ST30..35')
prove(And(b.st[33] == a.r[34], b.st[34] == a.r[35], b.st[35] == a.st[35]),
      '8C/double-restore/8D final ST33..35 = initial [R34,R35,ST35]')

a = State('pre8c')
b = compose(a, [0x4E,0x97,0x99,0x9B,0x9C,0x9E], 'pre8c_keys')
prove(b.r[35] == a.r[33],
      '4E routes old A.R33 into pre8C.R35; formatter commands preserve this source')

a = State('second_restore')
b = compose(a, [0x4E] + transport + [0x4E] + transport, 'second_keys')
prove(And(b.st[34] == a.st[33], *[b.r[n] == a.r[n] for n in positions]),
      'LOCAL two 4E+restore blocks retain six cache tetras and transfer initial ST33 into ST34')
print('LIMIT: the first block needs a native return before a second 4E; this local composition '+
      'does not supply that return and is not a partial-K2 repair.', flush=True)
