#!/usr/bin/env python3
"""Exact AC/93/A9 route: old PC becomes a command, not a native setup.

No return address is assigned. AC/E2/E3/92/E4 create all the return tags
used by the suffix. Ring data remain arbitrary: SAT is only a diagnostic.
All command-address constraints use a common execution and are checked
for consistency before reporting a field transport lemma.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ULT, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
stack = lambda a: tuple(byte(a.st[36+i], a.st[39+i]) for i in range(3))


def prove(p, claim, label):
    assert p.check() == sat, 'empty assumptions: '+label
    p.push()
    p.add(~claim)
    assert p.check() == unsat, label
    p.pop()
    print('PASS:', label, flush=True)


a = State('ac_a9_entry')
p = base(a, 0xAC)
p.add(Or(a.r[41] == 0, a.r[41] == 15))
b = a
sequence = tuple(int(v, 16) for v in
    'AC E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A '
    'E4 DE D6 E5 E6 E9 AD A9 93 94 95 98 9A E5 E6 E9'.split())
entries = []
key_terms = []
for index, ip in enumerate(sequence):
    p.add(address(b) == ip)
    assert p.check() == sat, ('inconsistent route at', index, ip)
    # Equivalent under the asserted address, and prevents large symbolic
    # address expressions from hiding the simple data transport.
    b = b.copy()
    b.r[36], b.r[39] = q['N4'](ip), q['N4'](ip >> 4)
    entries.append(b)
    signals = keys(f'ac_a9_keys_{index}')
    key_terms.extend(signals[0]+signals[1])
    b = execute(b, ip, *signals)
p.add(address(b) == 0xAD)
assert p.check() == sat

prove(p, And(a.st[35] == 9, b.r[2] == a.r[1],
             b.r[32] == a.r[31], b.r[35] == a.r[34],
             b.r[31] == 9, b.r[34] == a.st[32],
             *[v == n for v, n in zip(stack(b), (0x93, 0xE5, 0xAD))]),
      'AC/A9 route restores R2 from original R1; old PC becomes opcode; '
      'new PC is old ST32:9; all return tags are created by this route')
prove(p, And(b.r[0] == entries[5].m[1], entries[5].m[34] == 6),
      'needed R0 comes from EE input M1, and its M34 must be 6 for DE->D6')

# The four cycle handlers need precisely this previous PC signature.
cycle = And(UGE(b.r[2], 5), b.r[0] == 3, b.r[35] == 5,
            Or(*[b.r[32] == n for n in (8, 10, 11, 13)]))
p.push()
p.add(cycle)
assert p.check() == sat, 'cycle signature control'
prove(p, And(UGE(a.r[1], 5), a.r[34] == 5,
             Or(*[a.r[31] == n for n in (8, 10, 11, 13)]),
             entries[5].m[1] == 3),
      'high-mode cycle requires old PC in {58,5A,5B,5D}, R1>=5, EE M1=3')
p.pop()

# The preferred first source is old PC 58, which is ordinary decimal 58.
# The other three low nibbles are nondecimal. This test does not claim
# that any of these joint states has a keyboard preparation.
for low in (8, 10, 11, 13):
    p.push()
    p.add(cycle, a.r[31] == low, UGE(a.st[32], 12))
    assert p.check() == sat, ('high-counter cycle signature', low)
    p.pop()
print('PASS: all four artificial AC signatures remain compatible with '
      'a high restored counter. No real-ring or keyboard reachability '
      'is asserted.', flush=True)

# Join the newly derived prefix to the actual Ms gate, rather than merely
# matching separate projections of the handler and DD inputs.
p.add(cycle, a.r[31] == 8, UGE(a.st[32], 12))
suffix = tuple(int(v, 16) for v in
    'AD A5 1F 18 1B 1D 2E 01 02 02 02 03 04 BA CB '
    'DD D6 2F 21 22 36 37 38 06 07 6D 6F 62 6E 61 '
    '3A 06 07 6D 60 61 3A 06 07 6D 60 61 3A 06 07 6D 60'.split())
for index, ip in enumerate(suffix):
    p.add(address(b) == ip)
    assert p.check() == sat, ('inconsistent C8 suffix at', index, ip)
    b = b.copy()
    b.r[36], b.r[39] = q['N4'](ip), q['N4'](ip >> 4)
    b = execute(b, ip)  # Released keys throughout the suffix.
p.add(address(b) == 0xC8, *[term == 0 for term in key_terms])
assert p.check() == sat, 'whole AC-to-C8 path with released keys'
prove(p, And(b.r[38] == 4, b.r[26] != 0, b.r[25] == b.r[31],
             UGE(b.r[2], 5),
             *[v == n for v, n in zip(stack(b), (0x6E, 0x08, 0x3B))]),
      'whole old-PC-58 AC route reaches the C8 gate with genuine return tags')
print(f'PASS: {len(sequence)+len(suffix)} consecutive commands from artificial '
      'AC entry to C8, with released keys. The initial saved fields and '
      'subsequent ring inputs are NOT a physical preparation.', flush=True)
