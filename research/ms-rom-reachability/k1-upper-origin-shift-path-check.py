#!/usr/bin/env python3
"""Conditional ROM proof: D6(U) pushes P8/P9/P10/physical marker.

The ordinary P0 source and the four displaced target words (P8, P9,
P10, physical marker) are arbitrary twelve-tetra values. W is constrained
by W[22] == 15. This checks the IK1302 output transformation on ten
consecutive pages; the native audit separately covers all three chips.
The keyboard prefix, late formatter and eventual restoration of the real
marker are separate obligations. This is NOT a closed K1.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
seq = [0xD6, 0xA7, 0xE5, 0xE6, 0xE8, 0xE7, 0xA8, 0xA8, 0xA8, 0xA9]
names = ['U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10', 'marker', 'control', 'X1']
pages = [State('origin_push_page_' + n).m for n in names]
a = State('origin_push'); a.m = pages[0]; p = base(a, 0xD6)
p.add(byte(a.st[36], a.st[39]) == 0xA7,
      byte(a.st[37], a.st[40]) == 0xAC, pages[2][22] == 15)

def prove(claim, label):
    assert p.check() == sat, ('empty premises', label)
    p.push(); p.add(~claim); result = p.check()
    assert result == unsat, (label, p.model() if result == sat else result)
    p.pop()

b = a; carried = [pages[0][3*j] for j in range(12)]; written = {}
for i, ip in enumerate(seq):
    label = '%02X(%s)' % (ip, names[i])
    prove(address(b) == ip, label + ' forced address')
    out = []
    b = ex(b, ip, *keys('origin_push_keys_' + str(i)),
           serial_inputs=pages[i+1], emitted_outputs=out)
    if ip in (0xE7, 0xA8):
        prove(And(*[out[1+3*j] == carried[j] for j in range(12)],
                  *[out[j] == pages[i][j] for j in range(42) if j % 3 != 1 or j >= 37]),
              label + ' exact twelve numerical writes only')
        written[names[i]] = out
        carried = [pages[i][1+3*j] for j in range(12)]
        prove(And(*[b.r[3*j] == carried[j] for j in range(12)]),
              label + ' exact displaced word')
    else:
        prove(And(*[x == y for x, y in zip(out, pages[i])]), label + ' no ring writes')

assert list(written) == ['P8', 'P9', 'P10', 'marker']
prove(And(address(b) == 0xAC, b.s1 == 0,
          *[written['P8'][1+3*j] == pages[0][3*j] for j in range(12)],
          *[written[dst][1+3*j] == pages[names.index(src)][1+3*j]
            for dst, src in [('P9', 'P8'), ('P10', 'P9'), ('marker', 'P10')]
            for j in range(12)]), 'finite return and four exact transfers')
print('PASS ten connected ROM commands: ordinary P0 -> P8; P8 -> P9; P9 -> P10; P10 -> physical marker.', flush=True)
print('PASS arbitrary source/four displaced target words and key signals; four exact twelve-tetra transfers; other IK1302 output tetras held on these ten pages.', flush=True)
print('LIMIT: native entry and late formatting must be checked separately. Original-marker restoration and full K1 are NOT proved.', flush=True)
