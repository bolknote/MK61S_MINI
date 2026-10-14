#!/usr/bin/env python3
"""Complete ROM-wide classification of the R26 control nibble.

Uses exact 42-tick IK1302 semantics with arbitrary keyboard/ring inputs.
R26 is an internal field, not the user's calculator register P26.
"""
import runpy
from pathlib import Path

from z3 import sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))

groups = {
    'zero': (0x10, 0x14, 0x29, 0x76, 0x81, 0x86, 0x90, 0x9F, 0xAD,
             0xB1, 0xD1, 0xD8, 0xDE, 0xDF, 0xEF, 0xF0),
    'fifteen': (0x11, 0x2A, 0x2B, 0x51, 0xAB, 0xC2, 0xCA),
    'copy_R29': (0x08, 0x12, 0xC6, 0xEB),
    'copy_R25': (0x92, 0x9A),
    'R1_plus_one': (0x13, 0x62, 0x6F, 0xC4),
    'increment': (0x84,),
    'copy_S': (0xA4,),
}
labels = {ip: label for label, ips in groups.items() for ip in ips}
assert len(labels) == 35
for ip in range(256):
    a = State(f'r26_fact_{ip}')
    b = execute(a, ip, *keys(f'r26_fact_keys_{ip}'))
    label = labels.get(ip, 'preserve')
    expected = {'zero': 0, 'fifteen': 15, 'copy_R29': a.r[29],
                'copy_R25': a.r[25], 'R1_plus_one': a.r[1]+1,
                'increment': a.r[26]+1, 'copy_S': a.s,
                'preserve': a.r[26]}[label]
    p = base(a, ip)
    p.add(b.r[26] != expected)
    assert p.check() == unsat, (ip, label)
    if ip in labels:
        p = base(a, ip)
        p.add(b.r[26] != a.r[26])
        assert p.check() == sat, ('spurious writer', ip)
    if ip % 64 == 63:
        print(f'checked {ip+1}/256 R26 transfers', flush=True)
for label, ips in groups.items():
    print(label+': '+' '.join(f'{ip:02X}' for ip in ips), flush=True)
print('PASS: exactly 35 R26 writers; 221 commands preserve it. Additions '
      'are modulo 16. All nonconstant sources remain explicit; no Boolean '
      'or zero/fifteen-only invariant is assumed.', flush=True)
