#!/usr/bin/env python3
"""Exact D8 tail and cache transport: real93->ST1, first40->ST2.

The universal D8 component is proved on original words with fresh arbitrary
per-tick keys/serial inputs. Two paired conditional A3/CC/head93 contracts
vary all six opaque cache tetras, never a calculator state. Every return is
original; preliminary A3 and full BC writes are exposed. A common future
stream is not a whole-ring or native exchange claim. Earlier independent
reserves, other chips, original memory and different adapters remain open.
"""
from pathlib import Path
import runpy

from z3 import And, If, BitVecVal, sat, unsat

root = Path(__file__).resolve().parent
m = runpy.run_path(str(root / 'cache-bc-a3-cc-inlet-cut.py'))
r, w, q, old, A, B, C, eq = (m[n] for n in ('r', 'w', 'q', 'old', 'A', 'B', 'C', 'eq'))
raw = (0, 3, 9, 12, 18, 21)
tail = (0xD8, 0xF2, *((0xF3, 0xF7, 0xF1)*8),
        0xF4, 0xF6, 0xF4, 0xEA, 0xEC)
assert len(tail) == 31


def step(a, p, code, label, *, pins=None, serial=None):
    w['prove'](p, w['ip'](a) == code, label+' original IP', False)
    output = []
    b = w['ex'](a, code, *(pins if pins is not None else q['arbitrary_keys'](label+'_keys')),
        serial_inputs=serial if serial is not None else q['State'](label+'_serial').m,
        emitted_outputs=output)
    return b, output


def universal_d8():
    a = q['State']('head93_D8_any'); p = w['base'](a, 0xD8); b = a
    for i, code in enumerate(tail):
        before = b
        b, output = step(b, p, code, f'head93_D8_any_{i}')
        w['prove'](p, And(eq(output, before.m), eq(b.st[:36], a.st[:36])),
            'universal D8 tail no ring write or numericST change', False)
        if code == 0xD8:
            w['prove'](p, And(w['ip'](b) == 0xF2, *[v == 0 for v in B(b)],
                b.r[2] == 0, b.r[23] == 7, b.r[26] == 0, b.s1 == 0),
                'GLOBAL D8: B12zero, mode0, C7seven, counter0, S1zero')
        if i == 25:  # Last F1, after exactly eight F7 shifts.
            w['prove'](p, And(w['ip'](b) == 0xF4, b.r[23] == 15,
                eq(A(b), [a.r[24], *[q['N4'](15)]*7, q['N4'](0), *[q['N4'](15)]*3])),
                'GLOBAL D8 eight shifts: oldA8 survives inA0; remaining A is F/F/0/FFF, '
                'not arbitrary payload or a finished calculator')
    w['prove'](p, And(w['ip'](b) == 0x40, *[v == 0 for v in A(b)],
        eq(b.st[:36], a.st[:36])),
        'GLOBAL D8 original F4/F6/F4/EA/EC reaches40 with ZERO A12, numericST still held')
    z, output = step(b, p, 0x40, 'head93_D8_any_first40')
    w['prove'](p, And(w['ip'](z) == 0x41, *[v == 0 for v in z.st[0:36:3]],
        eq(z.st[1:36:3], a.st[0:36:3]), eq(z.st[2:36:3], a.st[1:36:3]),
        eq(output, b.m)), 'GLOBAL first40 overwrites numericST0 with ZERO, no ring write yet')
    print('PASS universal original D8 fixed31-word path through EC->40, '
          'then the32nd original word40; '
          'zero formatter inlet and first40 verified for ALL initial fields, '
          'keys and serial streams. No native factory or safe idle exit.', flush=True)


def single_restore():
    a = q['State']('head93_single_restore'); p = w['base'](a, 0x93); b = a
    for i, code in enumerate((0x93, 0x94, 0x95, 0x98, 0x9A)):
        before = b
        b, output = step(b, p, code, f'head93_single_restore_{i}')
        w['prove'](p, eq(output, before.m), 'single93 no ring write', False)
    w['prove'](p, And(eq(A(b), B(a)), eq(B(b), C(a)), eq(C(b), a.st[0:36:3]),
        eq(b.st[0:36:3], a.st[1:36:3]), eq(b.st[1:36:3], A(a)),
        eq(b.st[2:36:3], a.st[0:36:3])),
        'GLOBAL single93 numerical permutation: A->ST1, ST1->ST0; '
        'not a guessed save inST0 or destruction by94')


def original49_recovery():
    # A separate ORIGINAL component. Its real49 caller from the selected
    # D8/zero formatter is NOT assumed/proved by this recovery contract.
    a = q['State']('head93_49_cache_recovery'); p = w['base'](a, 0x49); b = a
    for i, code in enumerate((0x49, 0xBD, 0x91, 0x92, 0x93, 0x94, 0x95,
                             0x98, 0x9A, 0x93, 0x94, 0x95, 0x98, 0x9A)):
        before = b
        b, output = step(b, p, code, f'head93_49_cache_recovery_{i}')
        w['prove'](p, eq(output, before.m), 'original49 recovery no outgoing ring write', False)
    w['prove'](p, And(w['ip'](b) == 0xBE, eq(C(b), a.st[1:36:3]),
        eq(b.st[2:36:3], a.st[1:36:3]), eq(b.st[1:36:3], C(a))),
        'GLOBAL original49/BD/double91 promotes full cachedST1 into BOTH C andST2; '
        'real BE tag created, no replacement return')
    p.push(); p.add(a.st[31] == 2, a.st[34] == 13, a.r[26] == 0)
    w['prove'](p, And(b.st[32] == 2, b.st[35] == 13, b.st[25] == 0),
        'CONDITIONAL TYPE2 reserve promotion supplies future AC.ST32two/ST35D/ST25zero')
    p.pop()
    print('PASS original49 recovery gadget. This is NOT a native jump into49 '
          'or a proved contiguous D8/zero-formatter->49 connection; safe BE '
          'exit and physical inverse remain unproved.', flush=True)


def paired_head93(typ):
    label = f'head93_D8_cache_type{typ}'
    a = q['State'](label); other = q['State'](label+'_other'); paired = a.copy()
    for j in raw: paired.r[j] = other.r[j]
    p = w['base'](a, 0xA3)
    p.add(a.r[37] == 12, a.r[40] == 12, a.r[26] == 0,
        a.r[32] == typ, a.r[35] == 13, a.s1 == 9, a.r[34] == 6,
        *[w['stack'](a)[j] == n for j, n in enumerate((0x93, 0xE5, 0xAD))])
    if typ == 2: p.add(a.r[30] == 2, a.r[33] == 13)
    assert p.check() == sat
    b, c = a, paired
    prefix = (0xA3, 0xCC, 0xBB, 0xBC, 0x93, 0x94, 0x95, 0x98, 0x9A, 0xE5, 0xE6, 0xEA)
    for i, code in enumerate((*prefix, *tail, 0x40)):
        if code == 0xE5: p.add(b.m[22] == 15)
        pins = q['arbitrary_keys'](label+f'_keys{i}')
        serial = q['State'](label+f'_serial{i}').m
        before_b, before_c = b, c
        b, ob = step(b, p, code, label+f'_left{i}', pins=pins, serial=serial)
        c, oc = step(c, p, code, label+f'_right{i}', pins=pins, serial=serial)
        w['prove'](p, eq(ob, oc), 'no six-cache distinction exported to primary ring', False)
        if code == 0xA3:
            w['prove'](p, eq(ob[28:35:3], A(a)[9:]),
                'paired head93 preliminary A3 upper3 write accounted for', False)
        elif code == 0xBC:
            w['prove'](p, And(w['ip'](b) == 0x93,
                eq(ob[1:42:3], [*B(a), q['N4'](3), q['N4'](10)])),
                'paired head93 true BC payload/source, not a memory-neutral call', False)
        else:
            w['prove'](p, And(eq(ob, before_b.m), eq(oc, before_c.m)),
                'paired head93 other words no outgoing ring write', False)
        if i == 8:
            w['prove'](p, And(eq(b.st[1:36:3], A(a)), eq(c.st[1:36:3], A(paired))),
                'CONDITIONAL real93/94/95/98/9A parks ALL oldA12/cache in ST1, NOT ST0')
        if i >= 8 and code != 0x40:
            w['prove'](p, And(eq(b.st[1:36:3], A(a)), eq(c.st[1:36:3], A(paired))),
                f'CONDITIONAL word{i}/{code:02X} holds all12 cache tetras inST1', False)
        if code == 0x40:
            w['prove'](p, And(w['ip'](b) == 0x41, *[v == 0 for v in b.st[0:36:3]],
                eq(b.st[2:36:3], A(a)), eq(c.st[2:36:3], A(paired)),
                eq(b.st[1:36:3], a.st[1:36:3])),
                'CONDITIONAL head93 first40 PUSH saves ZERO inST0 while moving ALL12 cached '
                'tetras ST1->ST2; no data lost and no public register identity asserted')
            if typ == 2:
                w['prove'](p, And(b.st[32] == 2, b.st[35] == 13, b.st[25] == a.st[25]),
                    'CONDITIONAL TYPE2 after first40 has future AC saved-tail pair2/D; '
                    'saved counter is OLD A3.ST25, not automatically currentR26zero')
    print(f'PASS CONDITIONAL TYPE{typ}: six opaque second-read tetras '
          'survive real93/D8 inST1; first40 PUSH moves ALL12 intoST2. TYPE2 '
          'has ST32=2/ST35=D there; TYPE3 retains original upper tetras. No native '
          'source, readable public cache register, inverse or safe whole '
          'formatter return is asserted.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    single_restore()
    universal_d8()
    paired_head93(3)
    paired_head93(2)
    original49_recovery()
    r['inlet']['immutable_reference']()
    print('PASS head93 original D8 tail/cache reserve, references unchanged; '
          'component contracts only, no live/native state injection or full exchange.', flush=True)
