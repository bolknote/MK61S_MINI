#!/usr/bin/env python3
"""BC/49 bypasses40/47: exact source limits and conditional writer inlet.

This uses original control/return constructors, but does NOT construct a
keyboard type3 inlet or a physical Ms exchange. BC overwrites14 M2 tetras
without reading the displaced word. A/B variants restrict the later byte
toF0..FF; C allows all256, with a one-tetra-displaced M2 store.
"""
from pathlib import Path
import runpy

from z3 import And, UGE, ULE, sat

root = Path(__file__).resolve().parent
entry = runpy.run_path(str(root / 'cache-be-writer-entry.py'))
r, w, q = entry['r'], entry['w'], entry['q']
A, B, ST0, ST1 = (entry[n] for n in ('A', 'B', 'ST0', 'ST1'))
walk, double = entry['walk'], entry['double']


def bc_writer_families():
    for selector in (10, 11, 12):
        for offset in range(7):
            tag = f'{selector:X}'; label = f'bc_writer_{offset}_{tag}'
            a = q['State'](label); p = w['base'](a, 0x54); address = 84+offset
            p.add(a.r[29] == selector-6, UGE(a.r[32], 3), ULE(a.r[32], 14),
                  a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
                  a.st[30] == address % 10, a.st[33] == address // 10)
            branch = {10: (0xBA, 0xCC, 0xBB), 11: (0xBB,), 12: ()}[selector]
            sequence = (0x54, 0xB7, 0x45, 0x8B, 0x48, 0xB1, 0xB3,
                        *branch, 0xBC, 0x49, 0xBD, *double, 0xBE,
                        0x63, *([0x64]*13), 0x66)
            assert not {0x40, 0x47} & set(sequence)
            b = walk(a, p, sequence, label, only_ring_writer=0xBC)
            p.add(b.m[22] == 15)
            b = walk(b, p, (1, *([2]*13), 3, 4, 0xBA, 0xCC, 0xCD), label+'_wait')
            buffer = B(a) if selector == 12 else [*B(a)[1:12], q['N4'](15)]
            w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
                b.r[2] == 5, b.r[23] == 1, b.r[26] == 0,
                b.r[31] == address % 10, b.r[34] == address // 10,
                b.r[35] == offset, b.r[32] == 12, b.r[29] == 0, b.r[38] == 8, b.s1 == 9,
                w['eq'](A(b), buffer),
                w['eq'](ST0(b), [*A(a)[:9], *buffer[9:12]])),
                f'CONDITIONAL BC/{tag}/offset{offset}: original writerC9/67; '
                'numeric ST1 joint held through B3-clear, raw A lower9 reserved, no40/47')
            p.push()
            byte = q['BitVec'](label+'_source_byte', 8)
            p.add(w['byte'](b.r[30], b.r[33]) == byte)
            assert p.check() == sat
            assert q['possible_values'](byte, p, 257) == (
                list(range(256)) if selector == 12 else list(range(0xF0, 0x100)))
            p.pop()
    print('PASS21 BC/49 writer interfaces: A/B accept only16 F-high bytes; '
          'C accepts ALL256. BC/C writes(7,B0..B11,F), not aligned oldB14; '
          'A/B write oldB12+FA but49 sees a one-tetra-rotated input. '
          'These are PRIMARY contracts, not native type/source/page/exit or partialK2.', flush=True)


def matching_native_control(native):
    gate = native['gate']['state']['ik1302']
    assert gate['r'][29] == 6 and gate['r'][32] == 0
    assert [gate['st'][j] for j in (1, 22, 25)] == (
        [5, 1, 0] if native['report']['numericJoint'] else [0, 0, 0])
    # Exact observed native state: only R32 becomes3 in this detached model.
    # No return, PC, byte, numeric buffer or ROM is repaired.
    a = r['concrete_primary'](gate); a.r[32] = q['N4'](3)
    p = w['base'](a, 0x54)
    b = walk(a, p, (0x54, 0xB7, 0x45, 0x8B, 0x48, 0xB1, 0xB3,
        0xBC, 0x49, 0xBD, *double), native['report']['name']+'_TYPE3_ONLY_C', only_ring_writer=0xBC)
    w['prove'](p, And(w['ip'](b) == 0xBE,
        b.r[23] == (1 if native['report']['numericJoint'] else 0),
        b.r[30] == a.r[31], b.r[33] == a.r[34],
        b.r[31] == a.st[30], b.r[34] == a.st[33],
        w['eq'](ST0(b), A(a))),
        'HYPOTHETICAL type3 ONLY: originalBC/49/BE has actual byte90h/PC99h; '
        'joint C control opens63, C0 does not')


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    bc_writer_families()
    r['inlet']['immutable_reference']()
