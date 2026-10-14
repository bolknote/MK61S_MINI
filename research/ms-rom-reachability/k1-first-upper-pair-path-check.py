#!/usr/bin/env python3
"""Conditional IK1303 U-marker/request-14 -> exact Q/P7 numeric swap.

All twelve payload tetras are arbitrary. Native keyboard reachability,
the primary chip and a normal exit are separate obligations.
"""
import json
import runpy
import subprocess
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
rom = json.loads(subprocess.check_output([
    'node', '-e', 'console.log(JSON.stringify(require(process.argv[1])["ИК1303"]))',
    str(q['ROM_PATH'])], text=True))
q['execute_command'].__globals__.update(
    COMMANDS=rom['команды'], SYNCS=rom['синхропрограммы'], MICROS=rom['микрокоманды'])
State, ex, base, keys = (q[n] for n in (
    'State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
A = lambda a: [a.r[3*j] for j in range(12)]
B = lambda a: [a.r[1+3*j] for j in range(12)]
slots = ['marker', 'control', 'X1', 'X', 'Y', 'Z', 'T',
         'U', 'V', 'W', 'Q', 'P7', 'P8', 'P9', 'P10']
seq = [0x6E, 0x5E, 0x50, 0x52, 0x53, 0x4F, 0x41, 0x43, 0x4D, 0x60] + \
      [0x37]*6 + [0x27, 0x61, 0x4E, 0x2A]
names = [slots[(7+i) % 15] for i in range(len(seq)+1)]
pages = {n: State('first_upper_page_'+n).m for n in slots}
a = State('first_upper_pair')
a.m = pages['U']
p = base(a, 0x6E)
p.add(a.r[29] == 0, pages['U'][22] == 15,
      pages['V'][34] == 1, pages['V'][31] == 4,
      *[pages[n][22] != 15 for n in ['X1', 'X', 'Y', 'Z', 'T']])
source = [pages['P7'][1+3*j] for j in range(12)]


def prove(claim, label):
    assert p.check() == sat, ('empty premises', label)
    p.push()
    p.add(~claim)
    result = p.check()
    assert result == unsat, (label, p.model() if result == sat else result)
    p.pop()


b = a
for i, ip in enumerate(seq):
    label = '%02X(%s)' % (ip, names[i])
    prove(address(b) == ip, label+' forced address')
    if ip == 0x53:
        prove(And(b.l == 1, b.s1 == 6, b.r[32] == 5,
                  b.r[35] == 0, b.r[41] == 5),
              'prefix establishes every source-reader entry field')
    out = []
    b = ex(b, ip, *keys('first_upper_keys_'+str(i)),
           serial_inputs=pages[names[i+1]], emitted_outputs=out)
    if 4 <= i <= 7 or i == 17:
        prove(And(*[x == y for x, y in zip(A(b), source)]), label+' source retained in A')
    if 8 <= i <= 16:
        prove(And(*[x == y for x, y in zip(B(b), source)]), label+' source retained in B')
    if ip in (0x4E, 0x2A):
        incoming = source if ip == 0x4E else [pages['Q'][1+3*j] for j in range(12)]
        prove(And(*[out[1+3*j] == incoming[j] for j in range(12)],
                  *[b.r[3*j] == pages[names[i]][1+3*j] for j in range(12)],
                  *[out[j] == pages[names[i]][j] for j in range(42)
                    if j % 3 != 1 or j >= 37]), label+' exact numeric swap')
    elif ip == 0x27:
        prove(And(out[31] == 15,
                  *[out[j] == pages[names[i]][j] for j in range(42) if j != 31]),
              'ACK changes only V[31] from 4 to F')
    else:
        prove(And(*[x == y for x, y in zip(out, pages[names[i]])]), label+' no ring writes')
prove(address(b) == 0x39, 'finite return on physical P8')
print('PASS 20 connected IK1303 commands: U marker + V request 14 constructs '
      'the source entry and exchanges arbitrary Q/P7 words; only V[31] additionally changes.', flush=True)
print('LIMIT: no whole-keyboard timing/domain, primary-chip behavior or normal-exit theorem.', flush=True)
