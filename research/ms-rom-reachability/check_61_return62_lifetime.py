#!/usr/bin/env python3
"""Why the real return tag62 made by 61 does not retain selector9.

The 3A branch ejects it before a return; the 63 branch meets CD and
changes selector to 8 before a return. Fresh-key/ring data are arbitrary.
The completed reset projection separately excludes older-tag bypasses.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ULT, sat, unsat

m = runpy.run_path(str(Path(__file__).with_name('analyze_dd_stack_lifetime.py')))
q = m['model']()
State, execute, base, keys = (q[n] for n in ('State', 'execute', 'base', 'keys'))
address, stack = m['address'], m['stack']

for high in (False, True):
    a = State(f'return62_high_counter_{high}')
    p = base(a, 0x61)
    p.add(a.r[38] == 9, UGE(a.r[34], 12),
          UGE(a.r[2], 5) if high else ULT(a.r[2], 5))
    seq = (0x61, 0x3A, 0x06, 0x07)
    successors = (0x3A, 0x06, 0x07, 0x6D if high else 0x09)
    b = a
    for i, (ip, nxt) in enumerate(zip(seq, successors)):
        b = execute(b, ip, *keys(f'return62_high_counter_keys_{high}_{i}'))
        p.push()
        p.add(address(b) != nxt)
        assert p.check() == unsat, ('forced 61/3A prefix', high, ip)
        p.pop()
    assert p.check() == sat
    p.push()
    p.add(~And(*[v == n for v, n in zip(stack(b), (0x08, 0x3B, 0x62))]))
    assert p.check() == unsat
    p.pop()
    if high:
        b = execute(b, 0x6D, *keys('return62_high_mode_6d'))
        p.add(~And(Or(address(b) == 0x60, address(b) == 0x6F),
                   *[v == n for v, n in zip(stack(b), (0x6E, 0x08, 0x3B))]))
        assert p.check() == unsat
    else:
        b = execute(b, 0x09, *keys('return62_low_mode_09'))
        p.push()
        p.add(~And(Or(address(b) == 0x39, address(b) == 0x99),
                   *[v == n for v, n in zip(stack(b), (0x08, 0x3B, 0x62))]))
        assert p.check() == unsat
        p.pop()
        for ip, tag in ((0x39, 0x3A), (0x99, 0x9A)):
            p.push()
            p.add(address(b) == ip)
            c = execute(b, ip, *keys(f'return62_low_mode_{ip}'))
            p.add(~And(*[v == n for v, n in zip(stack(c), (tag, 0x08, 0x3B))]))
            assert p.check() == unsat
            p.pop()
print('PASS: 61->3A puts tag62 at the bottom by 07. High R2 ejects '
      'it in 6D; low R2 ejects it in either 39 or 99 after 09. '
      'No return consumes that tag first.', flush=True)

facts = 0
for ip, successors, old_s1, new_s1 in (
        (0x63, (0x64,), None, 0), (0x64, (0x64, 0x66), None, None),
        (0x66, (0x01,), None, 9), (0x01, (0x01, 0x02), 9, 9),
        (0x02, (0x02, 0x03), 9, 9), (0x03, (0x04,), 9, 9),
        (0x04, (0xBA,), 9, 9), (0xBA, (0xCC,), 9, 9), (0xCC, (0xCD,), 9, 9)):
    a = State(f'return62_fetch_{ip}')
    b = execute(a, ip, *keys(f'return62_fetch_keys_{ip}'))
    p = base(a, ip)
    p.add(a.r[38] == 9)
    if old_s1 is not None:
        p.add(a.s1 == old_s1)
    assert p.check() == sat
    p.add(~And(Or(*[address(b) == n for n in successors]), b.r[38] == 9,
               True if new_s1 is None else b.s1 == new_s1))
    assert p.check() == unsat, ('unclosed 63 fetch route', ip)
    facts += 1
a = State('return62_cd_overwrite')
b = execute(a, 0xCD, *keys('return62_cd_overwrite_keys'))
p = base(a, 0xCD)
p.add(a.r[38] == 9, a.s1 == 9)
assert p.check() == sat
p.add(~And(address(b) == 0xC9, b.r[38] == 8))
assert p.check() == unsat
print(f'PASS: {facts} universal facts close 63->64*->66->01*->02*->03 '
      '->04->BA->CC->CD. Its first return-capable continuation comes only '
      'after CD replaces selector9 by8. Waiting cannot avoid the overwrite.', flush=True)
