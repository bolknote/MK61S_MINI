#!/usr/bin/env python3
"""Accepted 9C(T), Z/U markers: copy arbitrary X to U, then return A3.

Native tests must supply this entry. The secondary chip and late numeric
formatter are separate obligations; this is not a whole-cycle theorem.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
address = lambda a: ZeroExt(4, a.r[36]) | (ZeroExt(4, a.r[39]) << 4)
slots = ['marker', 'control', 'X1', 'X', 'Y', 'Z', 'T', 'U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10']
seq = [0x9C, 0x9E, 0x9F, 0xA0] + [0xE5]*6 + [0xE6, 0xED, 0xEE, 0xA1, 0xE5, 0xE6, 0xE9] + [0xA2]*8
names = [slots[(6+i) % 15] for i in range(len(seq)+1)]
pages = {n: State('neutral_cleanup_page_'+n).m for n in slots}
a = State('neutral_cleanup'); a.m = pages['T']; p = base(a, 0x9C)
p.add(a.r[30] == 2, a.r[33] == 3,
      If(pages['T'][31] == 15, UGE(pages['T'][34], 1), UGE(pages['T'][34], 7)),
      *[pages[n][22] == 15 for n in ['marker', 'Z', 'U']],
      *[pages[n][22] != 15 for n in ['V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10']])


def prove(claim, label):
    assert p.check() == sat, ('empty premises', label)
    p.push(); p.add(~claim); answer = p.check()
    assert answer == unsat, (label, p.model() if answer == sat else answer)
    p.pop()


b = a
for i, ip in enumerate(seq):
    label = '%02X(%s)' % (ip, names[i])
    prove(address(b) == ip, label+' forced address')
    out = []
    b = ex(b, ip, *keys('neutral_cleanup_keys_'+str(i)),
           serial_inputs=pages[names[i+1]], emitted_outputs=out)
    if ip == 0xE9:
        prove(And(*[out[1+3*j] == pages['X'][1+3*j] for j in range(12)],
                  *[out[j] == pages['U'][j] for j in range(42) if j % 3 != 1 or j >= 37]),
              'E9 copies exactly all twelve X payload tetras to U; other lanes/service held')
    else:
        prove(And(*[x == y for x, y in zip(out, pages[names[i]])]), label+' no ring writes')
prove(address(b) == 0xA3, 'finite return to A3(control)')
print('PASS 25 connected primary commands: accepted 9C(T) -> EE(X) -> exact E9(U) -> A3(control).', flush=True)
print('LIMIT: entry, secondary SIGN, canonical late return and keyboard timing require separate checks.', flush=True)
