#!/usr/bin/env python3
"""Local single-word E9 writer after A1; not keyboard reachability.

Physical ring placement and the two possible initial EE sources must come
from the native test. No arbitrary success is inferred from SAT states.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
stack = lambda a: [byte(a.st[36+i], a.st[39+i]) for i in range(3)]

def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push(); p.add(~claim)
    result = p.check()
    assert result == unsat, (label, p.model() if result == sat else result)
    p.pop(); print('PASS:', label, flush=True)

a = State('guard_a1'); p = base(a, 0xA1)
b = ex(a, 0xA1, *keys('guard_a1_keys'))
prove(p, And(address(b) == 0xE5, b.s1 == 9, stack(b)[0] == 0xA2),
      'A1 selects the E9 writer and return A2 independently of the numeric source')

for label, names in [('clear_u', ['Y','Z','T','U','V']),
                     ('clear_x1', ['W','Q','P7','P8','P9','P10','marker','control','X1','X'])]:
    # Start one word after EE: the first physical name holds A1.
    pages = [State(label + '_' + n).m for n in names]
    a = State(label + '_start'); a.m = pages[0]; p = base(a, 0xA1)
    mark_index = len(names) - 4
    p.add(pages[mark_index][22] == 15)
    for i in range(1, mark_index): p.add(pages[i][22] != 15)
    sequence = [0xA1] + [0xE5] * mark_index + [0xE6, 0xE9]
    b = a
    for i, ip in enumerate(sequence):
        prove(p, address(b) == ip, label + ': %02X at %s' % (ip, names[i]))
        out = []
        b = ex(b, ip, *keys(label + '_keys_' + str(i)), serial_inputs=pages[i+1], emitted_outputs=out)
        if ip == 0xE9:
            prove(p, And(*[out[1+3*j] == a.r[3*j] for j in range(12)],
                         *[out[j] == pages[i][j] for j in range(42) if j % 3 != 1 or j >= 37]),
                  label + ': exactly 12 numeric tetras receive the A1 source; other lanes and service remain unchanged')
        else:
            prove(p, And(*[out[j] == pages[i][j] for j in range(42)]), label + ': no ring writes at %02X' % ip)
    prove(p, address(b) == 0xA2, label + ': returns to A2, not a four-word push')
# Connect the newly found false-T entrance to the zero source, without
# assuming any of the still-live U/V/W/Q numeric digits. The pending user
# opcode is 14h in R30/R33; this is observed at the native keyboard entry.
names = ['T','U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T','U','V']
pages_by_name = {n: State('guard_entry_page_' + n).m for n in set(names)}
a = State('guard_entry'); a.m = pages_by_name['T']; p = base(a, 0x9C)
p.add(a.r[30] == 4, a.r[33] == 1, pages_by_name['T'][34] == 9,
      pages_by_name['marker'][22] == 15, pages_by_name['Z'][22] == 15,
      *[pages_by_name[n][22] != 15 for n in ['Q','P7','P8','P9','P10']],
      *[pages_by_name['X'][1+3*j] == 0 for j in range(12)])
sequence = [0x9C,0x9E,0x9F,0xA0] + [0xE5]*6 + [0xE6,0xED,0xEE,0xA1,0xE5,0xE6,0xE9]
b = a
for i, ip in enumerate(sequence):
    prove(p, address(b) == ip, 'false-T entry: %02X at %s' % (ip, names[i]))
    out = []
    b = ex(b, ip, *keys('guard_entry_keys_' + str(i)), serial_inputs=pages_by_name[names[i+1]], emitted_outputs=out)
    if ip == 0xE9:
        prove(p, And(*[out[1+3*j] == 0 for j in range(12)],
                     *[out[j] == pages_by_name['U'][j] for j in range(42) if j % 3 != 1 or j >= 37]),
              'false-T entry: connected path sets only the twelve numeric U tetras to zero')
    else:
        prove(p, And(*[out[j] == pages_by_name[names[i]][j] for j in range(42)]),
              'false-T entry: ring unchanged at %02X' % ip)
prove(p, address(b) == 0xA2, 'false-T entry returns to A2 on V; no lower push')
print('LIMIT: connected ROM path and two local writer placements; a fixed keyboard preparation and safe whole-command return still require native tests.', flush=True)
