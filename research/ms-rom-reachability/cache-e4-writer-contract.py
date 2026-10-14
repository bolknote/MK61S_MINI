#!/usr/bin/env python3
"""Exact conditional A-source E4 formatter contract through writer and idle.

Entry metadata is matched by the keyboard-only P9/DC witness; entry E4 is NOT
native. No calculator setters, ROM changes or full-ring witness are used.
All six raw tetras, B, ST (except22), scalars and future ring/key inputs are
free, apart from released pins at33 and an eventual E5 marker. Native C-lane
metadata prevents inferring the formatter count from a random probe.
"""
from pathlib import Path
import runpy

from z3 import And, Or, Solver

root = Path(__file__).resolve().parent
d = runpy.run_path(str(root / 'cache46-bsource-exit.py'))
w = d['w']
State, ex, base, keys, ip, A, B, eq, prove = (w[name] for name in
    ('State', 'ex', 'base', 'keys', 'ip', 'A', 'B', 'eq', 'prove'))
N4 = w['q']['N4']
native_c = (8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 15)
source_indices = d['raw_indices']


def run(shifts, front_rotations):
    assert shifts in (0, 1, 2) and front_rotations in (1, 2, 3)
    label = f'front{front_rotations}_shift{shifts}'
    a = State(f'e4_writer_{label}')
    p = base(a, 0xE4)
    p.add(*[a.r[2+3*j] == v for j, v in enumerate(native_c)],
          a.r[6] == 15, a.r[15] == 15, a.r[24] == 15,
          a.r[27] == 10, a.r[30] == 9, a.r[33] == 9, a.st[22] == 0)
    if front_rotations == 1:
        p.add(a.r[0] != 0)
    elif front_rotations == 2:
        p.add(a.r[0] == 0, a.r[3] != 0)
    else:
        p.add(a.r[0] == 0, a.r[3] == 0)
    if shifts == 0:
        p.add(a.r[21] != 0)
    elif shifts == 1:
        p.add(a.r[21] == 0, a.r[18] != 0)
    else:
        p.add(a.r[21] == 0, a.r[18] == 0)
    source = A(a)
    prefix = (0xE4, 0xDE, 0xD9)
    prefix += (0xF3, 0xF7, 0xF1) * front_rotations + (0xF4,)
    prefix += (0xF6, 0xF4) * (9-front_rotations)
    sequence = prefix + (0xEA, 0xEC, 0x40, 0x41, 0x42)
    sequence += (0x44, 0x42) * shifts
    sequence += (0x46, 0xE5, 0xE5, 0xE6, 0xE8, 0xE7, 0x47, 0x49,
                 0xBD, 0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
                 0x93, 0x94, 0x95, 0x98, 0x9A, 0xBE, 0xB0, 0x33)
    pages = [State(f'e4_writer_{label}_page{j}').m
             for j in range(len(sequence)+1)]
    a.m = pages[0]
    b = a
    rotations = 0
    for j, code in enumerate(sequence):
        if code == 0xE5:
            p.add(pages[j][22] == (0 if sequence[j+1] == 0xE5 else 15))
        prove(p, ip(b) == code,
              f'E4/{label}: command{j} {code:02X} forced', False)
        if code == 0xEA:
            prove(p, And(eq(B(b), source), b.st[22] == 0),
                  f'E4/{label}: after9 B rotations reaches EA with exact original A12 in B')
        out = []
        pins = (0, 0) if code == 0x33 else keys(f'e4_writer_{label}_keys{j}')
        b = ex(b, code, *pins, serial_inputs=pages[j+1], emitted_outputs=out)
        if j < len(prefix):
            if code in (0xF7, 0xF6):
                rotations += 1
            expected = source[rotations % 9:9] + source[:rotations % 9] + source[9:]
            prove(p, eq(B(b), expected),
                  f'E4/{label}: prefix{j} B is exact9-tetra cyclic permutation, count{rotations}', False)
            prove(p, eq(b.st[:36], a.st[:36]),
                  f'E4/{label}: prefix{j} numeric ST untouched', False)
        if code == 0xE7:
            stored = out[1:36:3]
            expected = [N4(0)] * shifts + source[:8-shifts]
            expected += [N4(v) for v in (15, 10-shifts, 9, 9)]
            prove(p, And(eq(stored, expected),
                         eq(d['decode_raw_tetras'](stored, 10),
                            [source[k] for k in source_indices]),
                         eq(A(b), pages[j][1:36:3]),
                         *[out[t] == pages[j][t] for t in range(42)
                           if t % 3 != 1 or t >= 37]),
                  f'E4/{label}: one M2 write, reversible raw6, other lanes/services held')
        else:
            prove(p, eq(out, pages[j]),
                  f'E4/{label}: {code:02X} no outgoing ring write', False)
        if code == 0x47:
            prove(p, eq(A(b), source),
                  f'E4/{label}: 47 recovers original A12, before normalization')
    assert rotations == 9
    prove(p, And(ip(b) == 0x35, eq(b.st[:27:3], source[:9])),
          f'E4/{label}: exits35, raw6 held also in numeric ST lane0')
    print('CONDITIONAL A-SOURCE E4 WRITER, not native:', label,
          '; commands', len(sequence), '; B rotations9; end35.', flush=True)
    return a, b, p, sequence


if __name__ == '__main__':
    cover = State('e4_writer_case_cover')
    prove(Solver(), And(
        Or(cover.r[0] != 0, And(cover.r[0] == 0, cover.r[3] != 0),
           And(cover.r[0] == 0, cover.r[3] == 0)),
        Or(cover.r[21] != 0, And(cover.r[21] == 0, cover.r[18] != 0),
           And(cover.r[21] == 0, cover.r[18] == 0))),
        'three front and three tail data cases cover all six opaque raw tetras')
    for front_rotations in (1, 2, 3):
        for shifts in (0, 1, 2):
            run(shifts, front_rotations)
    print('PASS: all 256^3 raw three-byte patterns at conditional E4 entry. '
          'No native entry E4, physical Ms destination, old-Ms reserve or '
          'reverse program write is proved.', flush=True)
