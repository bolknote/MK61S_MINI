#!/usr/bin/env python3
"""Forced marker0->marker1 selector9 preparation feeds F into the read.

The counter-domain lemma and the selector9/07 fill invariant are proved
independently by check_selector9_shift.py. The failed-counter 63 lifetime
is checked separately. This script strengthens the selected SAT/UNSAT
path into a forced finite prefix, before unbounded read waits.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, sat, unsat

m = runpy.run_path(str(Path(__file__).with_name('analyze_dd_stack_lifetime.py')))
q = m['model']()
State, execute, base, keys = (q[n] for n in ('State', 'execute', 'base', 'keys'))
address, byte = m['address'], m['byte']

a = State('first_read_marker_identity')
p = base(a, 0x07)
p.add(a.r[26] == 0, a.r[38] == 9, UGE(a.r[2], 5))
b = a
for i, (ip, nxt) in enumerate(zip((0x07, 0x6D, 0x6F, 0x62), (0x6D, 0x6F, 0x62, 0x6E))):
    b = execute(b, ip, *keys(f'first_read_marker_identity_keys_{i}'))
    p.push()
    p.add(address(b) != nxt)
    assert p.check() == unsat, ('forced marker preparation', ip)
    p.pop()
assert p.check() == sat
p.add(b.r[26] != a.r[4]+1)
assert p.check() == unsat
print('PASS: 07->6D->6F->62->6E is forced from selector9/marker0/high R2; '
      'the resulting marker is the initial R4+1. Marker1 therefore '
      'requires initial R4=0.', flush=True)

seq = [int(s, 16) for s in (
    '07 6D 6F 62 6E 61 '
    '3A 06 07 6D 60 61 3A 06 07 6D 60 61 '
    '3A 06 07 6D 60 18 1B 1D 2E 01').split()]
allowed = {0} | set(range(0xC3, 0xCA)) | {16*h+l for h in (13, 14, 15) for l in range(10)}
a = State('first_read_forced_prefix')
p = base(a, 0x07)
p.add(a.r[26] == 0, a.r[38] == 9, UGE(a.r[2], 5), a.r[27] == 15,
      a.r[4] == 0, Or(*[byte(a.r[31], a.r[34]) == value for value in sorted(allowed)]))
assert p.check() == sat
b = a
for i, (ip, nxt) in enumerate(zip(seq, seq[1:])):
    b = execute(b, ip, *keys(f'first_read_forced_keys_{i}'))
    p.push()
    p.add(address(b) != nxt)
    assert p.check() == unsat, ('not a forced first-read edge', i, ip, nxt)
    p.pop()
assert p.check() == sat
p.add(~And(b.r[0] == 15, b.r[26] == 1, b.r[38] == 9,
           UGE(b.r[2], 5), b.r[32] == 2, b.s1 == 6))
assert p.check() == unsat
print(f'PASS: all {len(seq)-1} transitions through the third counter match '
      'and into 01 are forced for every admitted counter and arbitrary '
      'remaining data/keys/ring. The read starts with R0=F/R32=2/S1=6, '
      'not with a freely chosen payload digit.', flush=True)

for ip, successors in ((1, (1, 2)), (2, (2, 3)), (3, (4,)),
                       (4, (0xBA,)), (0xBA, (0xCB,)), (0xCB, (0xDD,))):
    a = State(f'first_read_wait_{ip}')
    b = execute(a, ip, *keys(f'first_read_wait_keys_{ip}'))
    p = base(a, ip)
    p.add(a.r[0] == 15, a.s1 == 6)
    assert p.check() == sat
    p.add(~And(b.r[0] == 15, b.s1 == 6,
               Or(*[address(b) == n for n in successors])))
    assert p.check() == unsat, ('unclosed read wait', ip)
print('PASS: any number of 01/02 waits preserves F through the whole '
      'read body. If it completes, its DD assigns selector0, never4 or9. '
      'The proof does not choose a read wait count or a key-release time.', flush=True)
