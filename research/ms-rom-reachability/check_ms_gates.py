#!/usr/bin/env python3
"""ROM-wide gate checks with independently changing keyboard pins each tick."""
import runpy
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
targets = [0xC7, 0xC8, 0xCD, 0xA3, 0x60, 0x68, 0x69, 0xFB, 0xFC, 0xFD, 0xFE, 0xF9]
pred = {target: [] for target in targets}
stack_pushes = []
for ip in range(256):
    state = State(f'dynamic_{ip}')
    final = execute(state, ip, *keys(f'key_{ip}'))
    solver = base(state, ip)
    new_ip = ZeroExt(4, final.r[36]) | (ZeroExt(4, final.r[39]) << 4)
    for target in targets:
        solver.push()
        solver.add(new_ip == target)
        outcome=solver.check()
        assert outcome in (sat,unsat),solver.reason_unknown()
        if outcome == sat:
            pred[target].append(ip)
        solver.pop()

    old_sp = [ZeroExt(4, state.st[36 + lane]) |
              (ZeroExt(4, state.st[39 + lane]) << 4) for lane in range(3)]
    new_sp = [ZeroExt(4, final.st[36 + lane]) |
              (ZeroExt(4, final.st[39 + lane]) << 4) for lane in range(3)]
    pushed = (ip & 0xf0) | ((ip + 1) & 0xf)
    identity = And(*[x == y for x, y in zip(new_sp, old_sp)])
    rotated = And(*[x == y for x, y in zip(new_sp, old_sp[1:] + old_sp[:1])])
    push = And(new_sp[0] == pushed, new_sp[1] == old_sp[0], new_sp[2] == old_sp[1])
    solver.push()
    solver.add(~Or(identity, rotated, push))
    assert solver.check() == unsat, f'unclassified stack transition at {ip:02X}'
    solver.pop()
    solver.add(push, ~identity, ~rotated)
    outcome=solver.check()
    assert outcome in (sat,unsat),solver.reason_unknown()
    if outcome == sat:
        stack_pushes.append(pushed)
    if ip % 64 == 63:
        print(f'checked {ip + 1}/256 commands', flush=True)

print('PASS: stack operations remain byte-preserving under arbitrary tick-level key changes')
common=[int(x,16) for x in '62 9A A3 A9 BC C7 C8 C9 CD D4 D6 E7 E9 EE'.split()]
assert pred[0xC7]==common
assert pred[0xC8]==[0x60]+common
assert 0xC8 not in stack_pushes
assert 0x60 not in stack_pushes
assert stack_pushes.count(0xC7)==1
print('PASS: complete C7/C8 predecessor sets and stack-creation restrictions')
print('stack can create:', ' '.join(f'{x:02X}' for x in sorted(stack_pushes)))
for target, sources in pred.items():
    print(f'predecessors({target:02X}):', ' '.join(f'{x:02X}' for x in sources))
