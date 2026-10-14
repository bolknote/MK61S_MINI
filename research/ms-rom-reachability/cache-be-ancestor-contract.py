#!/usr/bin/env python3
"""Original ancestors of49/82: exact byte, flag and address provenance.

All positive source paths are CONDITIONAL PRIMARY contracts, not a native
Ms supplier. An optional sign8 substitution is confined to a detached Z3
state and is tested as a NEGATIVE writer control, never a keyboard recipe.
"""
from pathlib import Path
import runpy

from z3 import And, If, UGE, UGT, ULE, sat

root = Path(__file__).resolve().parent
entry = runpy.run_path(str(root / 'cache-be-writer-entry.py'))
r, w, q = entry['r'], entry['w'], entry['q']
walk, double = entry['walk'], entry['double']
A, B, C, ST0, ST1 = (entry[n] for n in ('A', 'B', 'C', 'ST0', 'ST1'))
ST2 = lambda a: a.st[2:36:3]
N8 = entry['N8']


def first_restore_origin():
    a = q['State']('ancestor82_8C'); p = w['base'](a, 0x8C); out = []
    b = w['ex'](a, 0x8C, *q['arbitrary_keys']('ancestor82_8C_keys'), emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0x91, w['stack'](b)[0] == 0x8D,
        w['eq'](A(b), [*A(a)[:9], *ST0(a)[9:12]]),
        *[b.r[j] == a.r[j] for j in (2, 23, 26, 41)], w['eq'](out, a.m)),
        '8C itself replaces A upper3 from oldST0; lower9/cache held, original head8D')
    a = q['State']('ancestor82_first_restore'); p = w['base'](a, 0x8C)
    p.add(ULE(a.s1, 9))
    b = walk(a, p, (0x8C, *double, 0x8D), 'ancestor82_first_restore')
    w['prove'](p, And(w['ip'](b) == 0x8F,
        w['eq'](A(b), [*A(a)[:9], *ST0(a)[9:12]]),
        w['eq'](C(b)[:9], ST1(a)[:9]),
        w['eq'](ST1(b)[:9], C(a)[:9]),
        w['eq'](ST2(b)[:9], ST1(a)[:9]),
        b.r[26] == a.st[25], b.s == a.r[41], b.r[41] == a.r[41]),
        'first8F: byte=oldST0[10/11], sign=oldST1[8]; oldC lower9 reserved inST1')
    before = b
    b = w['ex'](b, 0x8F, *q['arbitrary_keys']('ancestor82_8F_keys'))
    w['prove'](p, And(w['ip'](b) == If(UGT(a.st[25], a.r[41]), N8(0x82), N8(0x81)),
        (And(w['ip'](b) == 0x82, b.r[26] == 8) ==
         And(a.st[25] == 8, ULE(a.r[41], 7))), w['eq'](A(b), A(before))),
        'direct original82/BD requires numeric ST1-sign8 AND lift flag0..7')
    # If8F selected81, its zeroing precludes BD at the first82, even when
    # the incoming saved sign was8. This is a gate, not a timing bound.
    for sign, flag_low, sequence in (
            (0, True, (0x8F, 0x81, 0x82)),
            (9, True, (0x8F, 0x82)),
            (9, False, (0x8F, 0x81, 0x82)),
            (8, False, (0x8F, 0x81, 0x82))):
        label = f'ancestor82_sign{sign}_{flag_low}'
        a = q['State'](label); p = w['base'](a, 0x8C)
        p.add(ULE(a.s1, 9), a.st[25] == sign)
        if sign == 0: pass
        elif flag_low: p.add(ULE(a.r[41], sign-1))
        else: p.add(UGE(a.r[41], sign))
        b = walk(a, p, (0x8C, *double, 0x8D, *sequence), label)
        w['prove'](p, And(w['ip'](b) == 0x84,
            w['eq'](b.r[0:27:3], a.r[0:27:3])),
            f'saved sign{sign}/lift{flag_low}: first82 chooses84, not BD; lower9 held')
    print('PASS canonical numeric C-sign0/9 cannot directly call BD via82. '
          'Even sign8 fails with lift>=8. Other inlets/later preparations remain open.', flush=True)


def two_restore_flag_origin():
    a = q['State']('ancestor82_two_restore'); p = w['base'](a, 0x8C)
    p.add(ULE(a.s1, 9), a.st[25] == 8, ULE(a.r[41], 7))
    b = walk(a, p, (0x8C, *double, 0x8D, 0x8F, 0x82, 0xBD, *double),
             'ancestor82_two_restore')
    w['prove'](p, And(w['ip'](b) == 0xBE,
        w['eq'](A(b), [*A(a)[:9], *ST0(a)[9:12]]),
        *[b.r[j] == a.r[j] for j in (2, 5, 23, 26, 31, 34)],
        w['eq'](ST0(b)[:9], ST0(a)[:9])),
        'two original91 calls restore PRE-8C mode/R23/R26/PC; byte from oldST0, not oldA')
    b = w['ex'](b, 0xBE, *q['arbitrary_keys']('ancestor82_two_restore_BE_keys'))
    w['prove'](p, w['ip'](b) == If(a.r[23] == 0, N8(0xB0), N8(0x63)),
        'BE decision after82 depends on PRE-8C R23, NOT ordinary numeric ST1[7]')
    print('PASS changing ordinary C flag only cannot repair a PRE-8C R23zero '
          'in this two-call82 path. Neither sign8 nor first91/joint5/1/0 is a writer.', flush=True)


def complete_82_writer_interfaces():
    for offset in range(7):
        label = f'ancestor82_writer_{offset}'
        a = q['State'](label); p = w['base'](a, 0x8C); address = 84+offset
        p.add(ULE(a.s1, 9), a.st[25] == 8, ULE(a.r[41], 7),
            UGE(a.r[2], 5), a.r[23] != 0, a.r[26] == 0,
            a.r[31] == address % 10, a.r[34] == address // 10)
        b = walk(a, p, (0x8C, *double, 0x8D, 0x8F, 0x82, 0xBD, *double,
            0xBE, 0x63, *([0x64]*13), 0x66), label+'_prefix')
        p.add(b.m[22] == 15)
        b = walk(b, p, (1, *([2]*13), 3, 4, 0xBA, 0xCC, 0xCD), label+'_wait')
        w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
            b.r[2] == a.r[2], b.r[23] == a.r[23], b.r[26] == 0,
            b.r[31] == address % 10, b.r[34] == address // 10,
            b.r[30] == a.st[30], b.r[33] == a.st[33],
            b.s1 == 9, b.r[29] == 0, b.r[38] == 8, b.r[32] == 12, b.r[35] == offset,
            w['eq'](A(b), [*A(a)[:9], *ST0(a)[9:12]]),
            w['eq'](ST0(b), ST0(a))),
            f'CONDITIONAL complete8C/82/offset{offset}: original writer-C9/67; '
            'byte from ST0/independent originalPC, lower9 A and ALL12 ST0 held')
        p.push()
        byte = q['BitVec'](label+'_all256', 8)
        p.add(w['byte'](a.st[30], a.st[33]) == byte)
        assert p.check() == sat
        w['prove'](p, w['byte'](b.r[30], b.r[33]) == byte, label+' byte formula', False)
        assert q['possible_values'](byte, p, 257) == list(range(256))
        p.pop()
    print('PASS seven nonempty upstream82 writer interfaces, ALL256 bytes each. '
          'Unlike a caller82-only contract, byte originates in oldST0 and flags '
          'in PRE-8C controlC. Native joint inlet/Ms provenance/page/exit are missing.', flush=True)


def original_47_conveyor():
    a = q['State']('ancestor49_47'); p = w['base'](a, 0x47)
    b = walk(a, p, (0x47, 0x49, 0xBD, *double), 'ancestor49_47')
    targets = (A(b), B(b), C(b), ST0(b), ST1(b), ST2(b))
    values = (B(a), ST1(a), ST2(a), ST0(a), C(a), ST2(a))
    w['prove'](p, And(w['ip'](b) == 0xBE,
        *[w['eq'](dst, src) for dst, src in zip(targets, values)]),
        '47/49/original91→BE: byte=oldB, address=oldST1, writer fields=oldST2')
    for code in (0x40, 0x41, 0x42, 0x46, 0xE5, 0xE6, 0xE8, 0xE7):
        a = q['State'](f'ancestor49_conveyor_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'ancestor49_conveyor_keys_{code:02X}'))
        expected = ST1(a)[:9] if code == 0x40 else ST2(a)[:9]
        w['prove'](p, w['eq'](ST2(b)[:9], expected),
            f'{code:02X} exact lower9 ST2 '+('overwrite from oldST1' if code == 0x40 else 'holder'), False)
    print('PASS native-shaped40→...→47 conveyor:40 replaces ST2 lower9 fromST1, '
          'holders retain it,47 rotates it toST1,full91 imports it to controlC. '
          'A joint ST2 value BEFORE40 is not a joint flag AFTER47/BE.', flush=True)


def native_sign8_counterfactual(native):
    # ONLY ST25 is changed, ONLY in a detached primary Z3 state.
    a = r['concrete_primary'](native['first8C']['state']['ik1302'])
    assert r['number'](a.r[23]) == 0 and r['number'](a.r[26]) == 0
    a.st[25] = q['N4'](8)
    for j in w['raw']: a.r[j] = q['BitVec'](native['report']['name']+f'_sign8_raw{j}', 4)
    p = w['base'](a, 0x8C)
    b = walk(a, p, (0x8C, *double, 0x8D, 0x8F, 0x82, 0xBD, *double, 0xBE),
             native['report']['name']+'_SIGN8_ONLY_HYPOTHESIS')
    w['prove'](p, And(w['ip'](b) == 0xB0, b.r[23] == 0,
        *[b.r[j] == a.r[j] for j in w['raw']]),
        'HYPOTHETICAL sign8 only: original82/BE still choosesB0, raw6 held; NOT writer')


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    first_restore_origin()
    two_restore_flag_origin()
    complete_82_writer_interfaces()
    original_47_conveyor()
    r['inlet']['immutable_reference']()
