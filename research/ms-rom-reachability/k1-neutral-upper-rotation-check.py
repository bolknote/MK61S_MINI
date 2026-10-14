#!/usr/bin/env python3
"""Connected IK1303 D4(V)..61 prepares the W/Q/P7/P8 rotation.

The numeric payloads are arbitrary. Native tests must validate the D4
entry; this proof excludes primary-chip concurrency and keyboard entry.
"""
import runpy
from pathlib import Path
from z3 import And
q = runpy.run_path(str(Path(__file__).with_name('check_ik1303_u_reader.py')))
State, ex, base, keys, address, prove, stack = (q[n] for n in
    ('State', 'execute', 'base', 'keys', 'address', 'prove', 'stack'))
names = ['V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10', 'marker', 'control', 'X1', 'X', 'Y', 'Z', 'T', 'U', 'V', 'W']
seq = [0xD4]*5 + [0xC4, 0x2C, 0x3B, 0x2B, 0x60] + [0x37]*4 + [0x27, 0x61]
pages = {n: State('neutral_rotate_page_'+n).m for n in set(names)}
a = State('neutral_rotate'); a.m = pages['V']; p = base(a, 0xD4)
p.add(a.l == 1, a.s1 == 9, a.r[37] == 4, a.r[38] == 0, a.r[40] == 13, a.r[41] == 6,
      *[x == v for x, v in zip(stack(a), [0x29, 0x3A, 0x3A])],
      *[a.r[2+3*i] == pages['W'][1+3*i] for i in range(12)],
      *[a.r[1+3*i] == pages['Q'][1+3*i] for i in range(12)],
      *[pages[n][22] != 15 for n in ['X', 'Y', 'Z']], pages['T'][22] == 15, pages['U'][31] == 15)
b = a
for i, ip in enumerate(seq):
    prove(p, address(b) == ip, 'forced %02X(%s)' % (ip, names[i]))
    out = []; b = ex(b, ip, *keys('neutral_rotate_keys_'+str(i)),
                    serial_inputs=pages[names[i+1]], emitted_outputs=out)
    prove(p, And(*[out[j] == pages[names[i]][j] for j in range(42)]), 'ring held at '+names[i])
prove(p, And(address(b) == 0x3A, b.s1 == 5,
             *[b.r[3*i] == pages['W'][1+3*i] for i in range(12)],
             *[b.st[3*i+lane] == pages[n][1+3*i]
               for lane, n in enumerate(['Q', 'P7', 'P8']) for i in range(12)]),
      'D4..61 prepares four arbitrary words and the output selector')
out_names = ['W', 'Q', 'P7', 'P8', 'P9']
for i, ip in enumerate([0x3A, 0x3A, 0x3A, 0x2A]):
    prove(p, address(b) == ip, 'forced output address at '+out_names[i])
    out = []; b = ex(b, ip, *keys('neutral_rotate_output_'+str(i)),
                    serial_inputs=pages[out_names[i+1]], emitted_outputs=out)
    source = pages[out_names[(i+1) % 4]]
    prove(p, And(*[out[1+3*j] == source[1+3*j] for j in range(12)],
                 *[out[j] == pages[out_names[i]][j] for j in range(42) if j % 3 != 1 or j >= 37]),
          'exact next-word copy at '+out_names[i])
prove(p, address(b) == 0x39, 'finite output return at P9')
print('PASS 20 connected IK1303 commands: exact W/Q/P7/P8 rotation for arbitrary 12-tetra payloads.', flush=True)
print('LIMIT: native entry, primary chip, formatting and cleanup remain separate obligations.', flush=True)
