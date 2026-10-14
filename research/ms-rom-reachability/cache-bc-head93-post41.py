#!/usr/bin/env python3
"""Contiguous head93 post41 formatter, true47 rotation and real49 recovery.

All positive formulas are CONDITIONAL PRIMARY contracts, not native keys or
physical Ms/programme identity. Actual A3/BC writes, the EXTRA zero E7 write,
and every original return are exposed. Paired cache words share other inputs;
old M2, earlier reserves and other chips are not globally identified/excluded.
No calculator-state/ROM/IP/return repair or loaded symbolic emulator state.
"""
from pathlib import Path
import runpy

from z3 import And, If, BitVecVal, Not, Or, sat, unsat

root = Path(__file__).resolve().parent
reserve = runpy.run_path(str(root / 'cache-bc-head93-d8-reserve.py'))
m, r, w, q, A, B, C, eq, raw = (reserve[n] for n in
    ('m', 'r', 'w', 'q', 'A', 'B', 'C', 'eq', 'raw'))

restore = (0x91, 0x92, 0x93, 0x94, 0x95, 0x98, 0x9A,
           0x93, 0x94, 0x95, 0x98, 0x9A)
post41 = (0x41, 0x43, 0x46, 0xE5, 0xE6, 0xE8, 0xE7,
          0x47, 0x49, 0xBD, *restore)
assert len(post41) == 22


def original_pair(b, c, p, code, label, *, quiet=False):
    pins = (0, 0) if quiet else q['arbitrary_keys'](label+'_keys')
    serial = q['State'](label+'_serial').m
    x, ox = reserve['step'](b, p, code, label+'_left', pins=pins, serial=serial)
    y, oy = reserve['step'](c, p, code, label+'_right', pins=pins, serial=serial)
    return x, y, ox, oy


def construct41(typ, label):
    a = q['State'](label); other = q['State'](label+'_other'); paired = a.copy()
    for j in raw: paired.r[j] = other.r[j]
    p = w['base'](a, 0xA3)
    p.add(a.r[37] == 12, a.r[40] == 12, a.r[26] == 0,
        a.r[32] == typ, a.r[35] == 13, a.s1 == 9, a.r[34] == 6,
        *[w['stack'](a)[j] == n for j, n in enumerate((0x93, 0xE5, 0xAD))])
    if typ == 2: p.add(a.r[30] == 2, a.r[33] == 13)
    assert p.check() == sat
    b, c = a, paired
    prefix = (0xA3, 0xCC, 0xBB, 0xBC, 0x93, 0x94, 0x95, 0x98, 0x9A,
              0xE5, 0xE6, 0xEA, *reserve['tail'], 0x40)
    for i, code in enumerate(prefix):
        if code == 0xE5: p.add(b.m[22] == 15)
        before_b, before_c = b, c
        b, c, ox, oy = original_pair(b, c, p, code, label+f'_inlet{i}')
        w['prove'](p, eq(ox, oy), 'prefix no cache distinction exported', False)
        if code == 0xA3:
            w['prove'](p, And(eq(ox[28:35:3], A(a)[9:]),
                *[ox[j] == before_b.m[j] for j in range(42) if j not in (28, 31, 34)]),
                'original preliminary A3 upper3 numericM2 write', False)
        elif code == 0xBC:
            w['prove'](p, And(w['ip'](b) == 0x93,
                eq(ox[1:42:3], [*B(a), q['N4'](3), q['N4'](10)]),
                *[ox[j] == before_b.m[j] for j in range(42) if j % 3 != 1]),
                'original BC14 numericM2/source services, true93', False)
        else:
            w['prove'](p, And(eq(ox, before_b.m), eq(oy, before_c.m)),
                'prefix other words ring neutral', False)
    w['prove'](p, And(w['ip'](b) == 0x41, w['ip'](c) == 0x41,
        eq(b.st[2:36:3], A(a)), eq(c.st[2:36:3], A(paired)),
        *[v == 0 for v in A(b)], b.r[26] == 0),
        'CONDITIONAL head93 actual full prefix reaches41, ZERO A, live cacheST2/counter0')
    return a, paired, b, c, p


def exact_post_gates():
    a = q['State']('post41_BE_gate'); p = w['base'](a, 0xBE)
    b, output = reserve['step'](a, p, 0xBE, 'post41_BE_gate')
    w['prove'](p, And(w['ip'](b) == If(a.r[23] == 0,
        BitVecVal(0xB0, 8), BitVecVal(0x63, 8)),
        eq(output, a.m)), 'GLOBAL BE guard is C7zero, otherwise63; ring held')
    w['prove'](p, And(eq(b.st[2:27:3], a.st[2:27:3]),
        eq(b.st[2:36:3][9:], a.st[1:36:3][9:]),
        eq(b.st[1:36:3][9:], a.st[0:36:3][9:]),
        eq(b.st[0:36:3][9:], A(a)[9:]), eq(C(b), C(a))),
        'GLOBAL BE pads only numericST upper3: ST2<-oldST1, ST1<-oldST0, '
        'ST0<-A; lower9 ST2/cache and workingC held')
    a = q['State']('post41_wait'); p = w['base'](a, 0xE5)
    b, output = reserve['step'](a, p, 0xE5, 'post41_wait')
    w['prove'](p, And(eq(b.st, a.st), b.s1 == a.s1,
        *[b.r[j] == a.r[j] for j in range(42) if j not in (36, 39)], eq(output, a.m)),
        'GLOBAL every finite E5 repeat keeps all reserve/data/tag fields; no fixed timing recipe')
    a = q['State']('post41_idle'); p = w['base'](a, 0x35)
    p.add(a.r[23] == 0, a.t == 0)
    b, output = reserve['step'](a, p, 0x35, 'post41_idle', pins=(0, 0))
    w['prove'](p, And(w['ip'](b) == 0x35, b.t == 0, b.r[23] == 0,
        eq(b.st[:36], a.st[:36]), eq(output, a.m)),
        'GLOBAL released-key35/C7zero/Tzero induction holds numericST and stays35 indefinitely')


def composed_return(typ):
    label = f'post41_composed_type{typ}'
    a, paired, b, c, p = construct41(typ, label)
    zero_write = None
    for i, code in enumerate(post41):
        if code == 0xE5: p.add(b.m[22] == 15)
        before_b, before_c = b, c
        b, c, ox, oy = original_pair(b, c, p, code, label+f'_return{i}')
        w['prove'](p, eq(ox, oy), 'post41 no cache distinction exported to primary ring', False)
        if code == 0xE7:
            zero_write = ox
            w['prove'](p, And(w['ip'](b) == 0x47, *[ox[j] == 0 for j in range(1, 36, 3)],
                *[ox[j] == before_b.m[j] for j in range(42) if j % 3 != 1 or j >= 36],
                eq(b.st[2:36:3], A(a)), eq(c.st[2:36:3], A(paired))),
                'CONDITIONAL genuine46/47 E7 writes EXTRA12 zero tetras to numericM2; cacheST2 held')
        else:
            w['prove'](p, And(eq(ox, before_b.m), eq(oy, before_c.m)),
                'post41 nonwriter has no primary ring write', False)
        if code == 0x47:
            w['prove'](p, And(w['ip'](b) == 0x49, eq(b.st[1:36:3], A(a)),
                eq(c.st[1:36:3], A(paired)), *[v == 0 for v in A(b)], b.r[26] == 0),
                'CONDITIONAL real47 rotates full cacheST2->ST1; zero inA andcounter0; real49 inlet')
    assert zero_write is not None
    w['prove'](p, And(w['ip'](b) == 0xBE, w['ip'](c) == 0xBE,
        eq(C(b), A(a)), eq(C(c), A(paired)),
        eq(b.st[2:36:3], A(a)), eq(c.st[2:36:3], A(paired)),
        b.st[25] == 0, b.r[23] == a.r[21]),
        'CONDITIONAL COMPLETE contiguous41->E7/47/49->realBE restores ALL12 cache intoC/ST2; '
        'future saved-counter25zero is now established, C7=RAW5')
    if typ == 2:
        w['prove'](p, And(b.st[32] == 2, b.st[35] == 13,
            b.r[32] == 2, b.r[35] == 13, b.st[25] == 0),
            'CONDITIONAL TYPE2 return produces entire future AC saved-tail0/2/D, no oldST25zero hypothesis')
    # These are the ORIGINAL two branches. No fake49/B0 return or repaired
    # dispatch makes the clean branch universal for an arbitrary RAW5.
    p.push(); p.add(a.r[21] != 0); assert p.check() == sat
    z, out = reserve['step'](b, p, 0xBE, label+'_nonzero_RAW5')
    w['prove'](p, And(w['ip'](z) == 0x63, eq(z.st[2:27:3], A(a)[:9]), eq(out, b.m)),
        'CONDITIONAL any RAW5nonzero takes63, NOT idle35; ALL six RAW/lower9 cache held, upper3 padded')
    p.pop()
    p.add(a.r[21] == 0, paired.r[21] == 0); assert p.check() == sat
    for i, code in enumerate((0xBE, 0xB0, 0x33)):
        before_b, before_c = b, c
        b, c, ox, oy = original_pair(b, c, p, code, label+f'_idle{i}', quiet=code == 0x33)
        w['prove'](p, And(eq(ox, before_b.m), eq(oy, before_c.m),
            eq(b.st[2:27:3], A(a)[:9]), eq(c.st[2:27:3], A(paired)[:9])),
            'clean subset original exit keeps all six RAW/lower9 cacheST2/no ring writes', False)
    w['prove'](p, And(w['ip'](b) == 0x35, w['ip'](c) == 0x35,
        eq(b.st[2:27:3], A(a)[:9]), eq(c.st[2:27:3], A(paired)[:9]),
        b.st[25] == 0, b.r[23] == 0, b.t == 0, c.t == 0),
        'CONDITIONAL RAW5zero/quiet33 actual controller35 with all six RAW/lower9 cache and saved-counterzero')
    w['prove'](p, And(b.st[32] == 0, b.st[25] == 0,
        Not(And(b.r[22] == 7, *[b.st[j] == 0 for j in range(1, 24, 3)]))),
        'CONDITIONAL actual35 savedTYPE is ZERO, not2/3; canonical C8 reader-ready packet absent')
    w['prove'](p, And(b.r[2] == 8, b.r[5] == a.r[0], b.r[22] == a.st[22],
        eq(b.st[1:24:3], [*[q['N4'](8)]*7, q['N4'](0)])),
        'CONDITIONAL exact35 metadata: mode8, savedMode=RAW0, Phi=oldA3.ST22; '
        'ST1lower8 = seven8 andzero, not canonicalzero controller data')
    # Expose readiness/mode, do not silently identify controller35 with a
    # safe calculator or claim canonical C8 reader readiness.
    for name, expr in [('mode2', b.r[2]), ('mode5', b.r[5]), ('flagB7', b.r[22])]:
        p.push(); values = q['possible_values'](expr, p, 17); p.pop()
        print(label, name, values, flush=True)
    print(f'PASS CONDITIONAL TYPE{typ}: contiguous writer/reserve/recovery/exit '
          'components joined, true tags throughout. ALL24 cache bits atBE; '
          'clean35 needs RAW5zero (20 independent bits) and released33 keys. '
          'BE pads upper3 and loses the savedTYPE2/D stamp before35; '
          'canonical reader readiness is absent. EXTRA zeroM2 write cannot be hidden. This conditional test asserts no native inlet, physical '
          'slot/all-register safety, inverse write or completeK2 claim.', flush=True)
    return a, paired, b, c, p


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    exact_post_gates()
    composed_return(3)
    composed_return(2)
    r['inlet']['immutable_reference']()
    print('PASS full head93 post41 primary composition; no reference/ROM/state edits '
          'or native/live/browser experiment.', flush=True)
