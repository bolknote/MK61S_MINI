#!/usr/bin/env python3
"""Exact raw-free D8 scrub at the real selector9/DC metadata.

This conditional primary contract permits every three-byte payload, arbitrary
per-tick keys and incoming serial pages. The native keyboard witness supplies
the metadata; no state setters or imagined jump into E4 are used. Pairing
covers R, ST, M, scalars and all outgoing ring values, not merely raw slots.
Original program bytes / earlier correlated reserves / other chips remain out
of scope. The shared incoming stream is NOT a full-ring collision proof.
"""
from pathlib import Path
import runpy

from z3 import And

root = Path(__file__).resolve().parent
w = runpy.run_path(str(root / 'cache46-writer-contracts.py'))
State, ex, base, keys, ip, A, B, eq, prove, same = (w[name] for name in
    ('State', 'ex', 'base', 'keys', 'ip', 'A', 'B', 'eq', 'prove', 'same'))
raw = (0, 3, 9, 12, 18, 21)
b_metadata = (0, 8, 8, 8, 8, 8, 8, 0, 0, 0, 9, 15)
c_metadata = (8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 15)
sequence = (0xDC, 0xEA, 0xD8, 0xF2)
sequence += (0xF3, 0xF7, 0xF1) * 8
sequence += (0xF4, 0xF6, 0xF4, 0xEA, 0xEC)


def main():
    a = State('d8_scrub_first')
    other = State('d8_scrub_other')
    paired = a.copy()
    for j in raw:
        paired.r[j] = other.r[j]
    p = base(a, 0xDC)
    p.add(*[a.r[1+3*j] == v for j, v in enumerate(b_metadata)],
          *[a.r[2+3*j] == v for j, v in enumerate(c_metadata)],
          *[a.r[j] == 15 for j in (6, 15, 24)],
          a.r[27] == 10, a.r[30] == 9, a.r[33] == 9)
    pages = [State(f'd8_scrub_page{j}').m for j in range(len(sequence)+1)]
    a.m = paired.m = pages[0]
    b, c = a, paired
    for j, code in enumerate(sequence):
        prove(p, And(ip(b) == code, ip(c) == code),
              f'D8 command{j} {code:02X} forced for both independent raw6 sets', False)
        pins = keys(f'd8_scrub_keys{j}')
        ob, oc = [], []
        b = ex(b, code, *pins, serial_inputs=pages[j+1], emitted_outputs=ob)
        c = ex(c, code, *pins, serial_inputs=pages[j+1], emitted_outputs=oc)
        prove(p, And(eq(ob, pages[j]), eq(oc, pages[j])),
              f'D8 command{j} {code:02X} no outgoing ring write', False)
        if code == 0xD8:
            prove(p, And(*[v == 0 for v in B(b)[:12]],
                          *[b.r[k] == a.r[k] for k in raw]),
                  'D8 zeros all12 B tetras while raw6 is still in A; no reserve')
        if j == 27:
            prove(p, And(eq(b.st[:36], a.st[:36]),
                          *[b.r[k] == 15 for k in range(0, 24, 3)],
                          b.r[24] == 0,
                          *[b.r[k] == 15 for k in (27, 30, 33)]),
                  'eight F7 shifts discard raw6; A=FFFFFFFF0FFF; numeric ST untouched')
    prove(p, And(ip(b) == 0x40, *[v == 0 for v in A(b)]),
          'natural EC reaches40 with all12 A tetras zero, not the raw cache')
    prove(p, same(b, c),
          'before40 entire primary R/ST/M/scalars agree for independent six raw input tetras')
    out = []
    d = ex(b, 0x40, *keys('d8_scrub_after_keys'), emitted_outputs=out)
    prove(p, And(ip(d) == 0x41, *[v == 0 for v in d.st[0:36:3]],
                  eq(out, b.m)),
          '40 saves ZERO, never these program codes; still no outgoing write')
    print('PASS: all256^3 payload patterns in the fixed selector9/DC metadata; '
          'forced scrub before40 under arbitrary per-tick keys/serial pages.', flush=True)
    print('LIMIT: local primary pair theorem with a common future stream; '
          'earlier reserves, original program memory, other chips and '
          'different entries are not excluded.', flush=True)


if __name__ == '__main__':
    main()
