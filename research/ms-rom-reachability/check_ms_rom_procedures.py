#!/usr/bin/env python3
"""Exact contracts for the surviving native Ms-related ROM procedures.

No keyboard reachability is inferred from an arbitrarily selected entry.
Register lane names here are zero-based; physical memory lanes are M1..M3.
"""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, ZeroExt, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
                            ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))
byte = lambda lo, hi: ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)
address = lambda a: byte(a.r[36], a.r[39])
top = lambda a: byte(a.st[36], a.st[39])


def prove(p, claims, label):
    p.push(); p.add(~And(*claims))
    assert p.check() == unsat, label
    p.pop()
    print('PASS:', label, flush=True)


for ip in (0xC7, 0xE7, 0xA8):
    a = State(f'swap_{ip}'); out = []
    b = execute(a, ip, *keys(f'swap_keys_{ip}'), emitted_outputs=out)
    p = base(a, ip)
    prove(p, [b.r[3*i] == a.m[1+3*i] for i in range(12)] +
             [out[1+3*i] == a.r[3*i] for i in range(12)] +
             [out[i] == a.m[i] for i in range(42)
              if i % 3 != 1 or i >= 37],
          f'{ip:02X}: exact 12-tetrade R-lane-0/M2 exchange, no other memory write')
    prove(p, [b.s1 == a.s1+2], f'{ip:02X} also increments S1 by two')
    if ip == 0xA8:
        prove(p, [b.s1 == a.s1+2,
                  address(b) == If(a.s1 == 14, BitVecVal(0xA9, 8), BitVecVal(0xA8, 8))],
              'A8 loop: S1 += 2 (mod 16); exits only from initial S1=E')
    else:
        prove(p, [address(b) == top(a)], f'{ip:02X} returns through the address stack')

# Compare complete state and every outgoing nibble with the same inputs;
# only the entry IP differs. Equal words alone do not prove such equivalence.
a = State('alias_c7_e7'); other = a.copy()
other.r[36], other.r[39] = q['N4'](7), q['N4'](14)
key_inputs = keys('alias_keys'); serial = State('alias_serial').m
out_c7, out_e7 = [], []
b = execute(a, 0xC7, *key_inputs, serial_inputs=serial, emitted_outputs=out_c7)
c = execute(other, 0xE7, *key_inputs, serial_inputs=serial, emitted_outputs=out_e7)
claims = [x == y for group in ('r', 'm', 'st')
          for x, y in zip(getattr(b, group), getattr(c, group))]
claims += [getattr(b, name) == getattr(c, name) for name in ('s', 's1', 'l', 't', 'carry')]
claims += [x == y for x, y in zip(out_c7, out_e7)]
prove(base(a, 0xC7), claims, 'C7 and E7 are universally identical, including return and all 42 outputs')

for ip, source_lane, target_lane, count in ((0xC8, 1, 1, 14), (0xD6, 0, 0, 12)):
    a = State(f'read_{ip}'); out = []
    b = execute(a, ip, *keys(f'read_keys_{ip}'), emitted_outputs=out)
    prove(base(a, ip),
          [b.r[target_lane+3*i] == a.m[source_lane+3*i] for i in range(count)] +
          [out[i] == a.m[i] for i in range(42)] + [address(b) == top(a)],
          f'{ip:02X}: read {count} tetras from M{source_lane+1}, preserve memory, return')

a = State('program_swap'); out = []
b = execute(a, 0xC9, *keys('program_swap_keys'), emitted_outputs=out)
prove(base(a, 0xC9),
      [b.r[1+3*i] == a.m[2+3*i] for i in range(14)] +
      [out[2+3*i] == a.r[1+3*i] for i in range(14)] +
      [out[i] == a.m[i] for i in range(42) if i % 3 != 2] +
      [address(b) == top(a)],
      'C9: exact 14-tetrade R-lane-1/M3 exchange, no other memory write, return')

# Both are natural two-command continuations. In DD's case S1=4 is a
# required parameter; the test does not claim it can be set by arbitrary keys.
for entry, writer, lane, count, selector in ((0xBB, 0xBC, 1, 14, None),
                                            (0xDD, 0xD4, 0, 12, 4)):
    a = State(f'store_{entry}'); p = base(a, entry); first = []; second = []
    if selector is not None: p.add(a.s1 == selector)
    b = execute(a, entry, *keys(f'store_prep_{entry}'), emitted_outputs=first)
    prove(p, [address(b) == writer], f'{entry:02X} naturally continues at {writer:02X}')
    c = execute(b, writer, *keys(f'store_write_{entry}'), emitted_outputs=second)
    prove(p, [first[i] == a.m[i] for i in range(42)] +
          [second[lane+3*i] == a.r[lane+3*i] for i in range(count)] +
          [second[i] == b.m[i] for i in range(42)
           if i % 3 != lane or i >= lane+3*count] +
          [address(c) == top(a)],
          f'{entry:02X}->{writer:02X}: aligned {count}-tetrade store to M{lane+1}, then return')

for ip, target in ((0x6A, 0x6B), (0x6B, 0x6C), (0xBB, 0xBC)):
    a = State(f'prep_alias_{ip}')
    b = execute(a, ip, *keys(f'prep_alias_keys_{ip}'))
    prove(base(a, ip), [address(b) == target],
          f'{ip:02X} has BB\'s ROM word but its own continuation {target:02X}')

for sequence in ((0x15, 0x0F, 0xD3), (0x16, 0x3F, 0xD3)):
    a = State(f'reserved_{sequence[0]}'); b = a; p = base(a, sequence[0])
    for n, (ip, target) in enumerate(zip(sequence, sequence[1:])):
        out = []; before = b
        b = execute(b, ip, *keys(f'reserved_{sequence[0]}_{n}'), emitted_outputs=out)
        prove(p, [address(b) == target] + [out[i] == before.m[i] for i in range(42)],
              f'reserved entry {ip:02X}->{target:02X}: unconditional, no outgoing memory write')

print('All local procedure contracts passed. None asserts a complete K1/K2 bank loop.', flush=True)
