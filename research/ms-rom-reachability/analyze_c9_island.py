#!/usr/bin/env python3
"""Inspect the exact control slice while C9 parks the numeric word in M3.

Local ROM semantics only: this does not assert keyboard reachability.
"""
import runpy
from pathlib import Path
from z3 import simplify, sat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
fields = (2, 26, 29, 32, 35, 38)
for ip in (0x67, 0x68, 0x69, 0x6A, 0x6B, 0x6C, 0xFB, 0xFD, 0xFE, 0xFC):
    a = q['State'](f'c9island_{ip:02x}')
    b = q['execute_command'](a, ip, *q['arbitrary_keys'](f'c9keys_{ip:02x}'))
    p = q['base_solver'](a, ip)
    p.add(a.r[2] == 5, a.r[26] == 9, a.r[38] == 8)
    address = q['ZeroExt'](4, b.r[36]) | (q['ZeroExt'](4, b.r[39]) << 4)
    p.push()
    successors = q['possible_values'](address, p)
    p.pop()
    print(f'{ip:02X}: next={" ".join(f"{v:02X}" for v in successors)}', flush=True)
    for name, old, value in [*(('R'+str(i), a.r[i], b.r[i]) for i in fields),
                              ('S1', a.s1, b.s1)]:
        p.push()
        p.add(value != old)
        changed = p.check() == sat
        p.pop()
        if not changed:
            continue
        p.push()
        values = q['possible_values'](value, p, 17)
        p.pop()
        print(f'  {name}: possible={values}; expression={simplify(value)}', flush=True)
