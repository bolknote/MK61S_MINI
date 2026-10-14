#!/usr/bin/env python3
"""Complete ROM source coverage for the 2E read helper, before first C7/C8.

The A3 vector bound is the independently completed reset invariant, not
an assumption about arbitrary chip states. No keyboard protocol is claimed.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ULE, sat, unsat

m = runpy.run_path(str(Path(__file__).with_name('analyze_dd_stack_lifetime.py')))
q = m['model']()
State, execute, base, keys = (q[n] for n in ('State', 'execute', 'base', 'keys'))
address, stack, byte = (m[n] for n in ('address', 'stack', 'byte'))

sources, pushers = [], []
for ip in range(256):
    a = State(f'read_source_{ip}')
    b = execute(a, ip, *keys(f'read_source_keys_{ip}'))
    p = base(a, ip)
    old, new = stack(a), stack(b)
    pushed = (ip & 0xF0) | ((ip+1) & 15)
    for kind, expected in [('same', old), ('rotate', old[1:]+old[:1]),
                           ('push', [pushed]+old[:2])]:
        p.push()
        p.add(~And(*[v == w for v, w in zip(new, expected)]))
        valid = p.check() == unsat
        p.pop()
        if valid:
            break
    else:
        raise AssertionError(('unknown stack transform', ip))
    if kind == 'push' and pushed == 0x2E:
        pushers.append(ip)
    p.add(address(b) == 0x2E, *[v != 0x2E for v in old])
    result = p.check()
    assert result in (sat, unsat)
    if result == sat:
        sources.append(ip)
assert sources == [0x1D, 0x2C, 0x36, 0xA3], sources
assert not pushers, pushers
print('PASS: all 256 sources and whole-stack transforms; no command can '
      'push return tag 2E. Non-return sources: 1D/2C/36/A3.', flush=True)

a = State('read_source_a3')
b = execute(a, 0xA3, *keys('read_source_a3_keys'))
p = base(a, 0xA3)
p.add(Or(a.r[37] == a.r[40], *[byte(a.r[37], a.r[40]) == n
         for n in (0x90, 0x93, 0xCC, 0xD3, 0xD8)]))
assert p.check() == sat
p.add(address(b) == 0x2E)
assert p.check() == unsat
print('PASS: independent first-entry A3 vector invariant excludes A3->2E. '
      'From zero reset, only 1D/2C/36 remain.', flush=True)

for ip in (0x1D, 0x2C, 0x36):
    a = State(f'read_source_mode_{ip}')
    b = execute(a, ip, *keys(f'read_source_mode_keys_{ip}'))
    p = base(a, ip)
    p.add(~And(b.r[2] == a.r[2], b.r[26] == a.r[26]))
    assert p.check() == unsat
    print(f'PASS: {ip:02X} preserves R2 and R26 on every branch.', flush=True)
    p = base(a, ip)
    expected = (ULE(a.r[26], 1) if ip == 0x1D else
                a.r[26] == 8 if ip == 0x36 else True)
    p.add((address(b) == 0x2E) != expected)
    assert p.check() == unsat
print('PASS: 1D->2E iff R26<=1; 2C->2E unconditional; 36->2E iff R26=8. '
      'The short high-mode DD suffix requiring R26=1 cannot be supplied '
      'by this direct 36->2E reread. Longer continuations remain open.', flush=True)
