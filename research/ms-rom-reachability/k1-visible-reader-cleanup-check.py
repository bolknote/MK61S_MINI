#!/usr/bin/env python3
"""Local D6(U) -> AC(V) cleanup retaining two independent visible words.

Entry is supplied by native keyboard traces, not assumed to be reachable
for all timings here. P0, Y, Z and the discarded old T are arbitrary words.
The numerical formatter and the entire reader are outside this theorem.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in (
    'State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
slots = ['marker', 'control', 'X1', 'X', 'Y', 'Z', 'T',
         'U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10']
seq = [0xD6, 0xA7] + [0xE5] * 7 + [0xE6, 0xE8, 0xE7,
                                      0xA8, 0xA8, 0xA8, 0xA9]
names = [slots[(7 + i) % 15] for i in range(len(seq) + 1)]
pages = {n: State('visible_cleanup_' + n).m for n in slots}
a = State('visible_cleanup')
a.m = pages['U']
p = base(a, 0xD6)
p.add(byte(a.st[36], a.st[39]) == 0xA7,
      byte(a.st[37], a.st[40]) == 0xAC)
for n in ['W', 'Q', 'P7', 'P8', 'P9', 'P10', 'marker']:
    p.add(pages[n][22] == 15 if n == 'marker' else pages[n][22] != 15)
p.add(*[pages['X'][1 + 3*j] == 0 for j in range(12)])
source = [pages['U'][3*j] for j in range(12)]


def prove(claim, label):
    assert p.check() == sat, ('empty premises', label)
    p.push()
    p.add(~claim)
    result = p.check()
    assert result == unsat, (label, p.model() if result == sat else result)
    p.pop()


b, carried, written = a, source, {}
for i, ip in enumerate(seq):
    label = '%02X(%s)' % (ip, names[i])
    prove(address(b) == ip, label + ' forced address')
    out = []
    b = ex(b, ip, *keys('visible_cleanup_keys_' + str(i)),
           serial_inputs=pages[names[i + 1]], emitted_outputs=out)
    if ip in (0xE7, 0xA8):
        prove(And(*[out[1 + 3*j] == carried[j] for j in range(12)],
                  *[out[j] == pages[names[i]][j] for j in range(42)
                    if j % 3 != 1 or j >= 37]),
              label + ' exact twelve-tetra swap')
        written[names[i]] = out
        carried = [pages[names[i]][1 + 3*j] for j in range(12)]
        prove(And(*[b.r[3*j] == carried[j] for j in range(12)]),
              label + ' exact displaced word')
    else:
        prove(And(*[x == y for x, y in zip(out, pages[names[i]])]),
              label + ' no ring writes')
assert list(written) == ['X', 'Y', 'Z', 'T']
prove(And(address(b) == 0xAC, b.s1 == 0,
          *[written['X'][1 + 3*j] == source[j] for j in range(12)],
          *[written['Y'][1 + 3*j] == 0 for j in range(12)],
          *[written['Z'][1 + 3*j] == pages['Y'][1 + 3*j] for j in range(12)],
          *[written['T'][1 + 3*j] == pages['Z'][1 + 3*j] for j in range(12)]),
      'P0/0/oldY/oldZ, old T discarded, X1 and all stored banks held')
print('PASS 16 connected commands: P0/0/arbitrary Y/arbitrary Z survive as '
      'X/Y/Z/T; old T alone is discarded; exactly 48 numeric writes.', flush=True)
print('LIMIT: local entry contract, not whole keyboard timing, formatter '
      'or retry convergence.', flush=True)
