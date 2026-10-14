#!/usr/bin/env python3
"""Exact local provenance and a labelled AC.ST32=4 causal hypothesis.

The only native runs are keyboard-only passive audits in the companion file.
Symbolic route replay is local semantics, not a native reachability claim.
"""
import json
import subprocess
from pathlib import Path
from z3 import Or, Solver, UGE, ZeroExt, unsat, simplify
from ik1302_symbolic import State, N4, N1, execute_command, base_solver


def address(state):
    return ZeroExt(4, state.r[36]) | (ZeroExt(4, state.r[39]) << 4)


def prove_equal(actual, expected, label):
    solver = Solver()
    solver.add(actual != expected)
    assert solver.check() == unsat, label
    print('PASS:', label)


def concrete(snapshot):
    state = State('native_ac')
    for group in ('r', 'st', 'm'):
        setattr(state, group, [N4(v) for v in snapshot[group]])
    for name in ('s', 's1'):
        setattr(state, name, N4(snapshot[name]))
    for name in ('l', 't', 'carry'):
        setattr(state, name, N1(snapshot[name]))
    return state


script = Path(__file__).with_name('st34-origin-trace.cjs')
events = json.loads(subprocess.check_output(
    ['node', str(script), '--proof-input'], text=True))['events']
assert events[0]['ip'] == 0xAC and events[-1]['ip'] == 0xC8
assert events[0]['st'][32] == 15

# Unrestricted local state and fresh arbitrary serial input prove independence
# from the earlier ST34, Ms payload, decimal sign, and lowDigit preparation.
initial = State('origin')
state = initial
before_bootstrap_61 = None
for event in events[:-1]:
    if event['ip'] == 0x61 and before_bootstrap_61 is None:
        before_bootstrap_61 = state
    state = execute_command(state, event['ip'], event['keyX'], event['keyY'])
prove_equal(state.st[34], initial.st[32],
            'full recorded AC-to-C8 route has final ST34 = initial ST32')
prove_equal(state.st[33], initial.r[35],
            'full recorded AC-to-C8 route has final ST33 = initial R35 (recall selector)')
prove_equal(state.st[35], initial.r[34],
            'full recorded AC-to-C8 route has final ST35 = initial R34 (high PC)')
assert before_bootstrap_61 is not None
gate = execute_command(before_bootstrap_61, 0x61)
solver = Solver()
solver.add(before_bootstrap_61.r[36] == 1, before_bootstrap_61.r[39] == 6,
           Or(*[initial.st[32] == v for v in range(1, 9)]), address(gate) != 0x63)
assert solver.check() == unsat
print('PASS: any AC source ST32 in 1..8 forces bootstrap 61->63 on this local route')

# Establish that the concrete local implementation reproduces the unmodified
# native command stream; all serial inputs and key signals are passive reads.
state = concrete(events[0])
for index, event in enumerate(events[:-1]):
    nxt = events[index + 1]
    state = execute_command(state, event['ip'], event['keyX'], event['keyY'],
                            serial_inputs=[N4(v) for v in nxt['m']])
    for group in ('r', 'st', 'm'):
        assert [simplify(v).as_long() for v in getattr(state, group)] == nxt[group], (index, group)
    for name in ('s', 's1', 'l', 't', 'carry'):
        assert simplify(getattr(state, name)).as_long() == nxt[name], (index, name)
print('PASS: exact concrete local replay matches all native IK1302 fields at every command')

# Explicitly hypothetical modification of a LOCAL symbolic State only.
# Stop at the first changed dispatch; do not force the native route afterward.
state = concrete(events[0])
state.st[32] = N4(4)
divergence = None
changed_ring_output = None
baseline = concrete(events[0])
for index, event in enumerate(events[:-1]):
    nxt = events[index + 1]
    outputs = []
    state = execute_command(state, event['ip'], event['keyX'], event['keyY'],
                            serial_inputs=[N4(v) for v in nxt['m']], emitted_outputs=outputs)
    baseline_outputs = []
    baseline = execute_command(baseline, event['ip'], event['keyX'], event['keyY'],
                               serial_inputs=[N4(v) for v in nxt['m']], emitted_outputs=baseline_outputs)
    if changed_ring_output is None:
        changes = [i for i in range(42) if not outputs[i].eq(baseline_outputs[i])]
        if changes:
            changed_ring_output = {'step': index, 'ip': event['ip'], 'ticks': changes}
    actual = simplify(address(state)).as_long()
    if actual != nxt['ip']:
        divergence = {'step': index, 'ip': event['ip'], 'hypothesisNext': actual,
                      'nativeNext': nxt['ip'], 'r34': simplify(state.r[34]).as_long(),
                      'st34': simplify(state.st[34]).as_long()}
        break
assert divergence == {'step': 103, 'ip': 0x61, 'hypothesisNext': 0x63,
                      'nativeNext': 0x3A, 'r34': 4, 'st34': 4}, divergence
print('PASS: LOCAL AC.ST32=4 hypothesis first diverts at step 103, 61->63 instead of 3A')
print('LOCAL hypothesis first altered ring output:', json.dumps(changed_ring_output))
assert changed_ring_output is None
print('PASS: the local hypothesis emits the same ring data until its first changed dispatch')

# The branch predicates are universal single-command identities, independent
# of ring input and the remaining state. Their accepted sets do not overlap.
a = State('gate61')
b = execute_command(a, 0x61)
solver = base_solver(a, 0x61)
solver.add((address(b) == 0x3A) != UGE(a.r[34], 12))
assert solver.check() == unsat
print('PASS: bootstrap 61->3A iff R34 is C..F')
a = State('gate_dc')
b = execute_command(a, 0xDC)
solver = base_solver(a, 0xDC)
solver.add((address(b) == 0xDE) != Or(*[a.r[34] == v for v in range(1, 9)]))
assert solver.check() == unsat
print('PASS: DC->DE iff R34 is 1..8; zero and 9..F go to EA')
print('PASS: the fixed bootstrap source C..F cannot also supply the later DC source 1..8')
