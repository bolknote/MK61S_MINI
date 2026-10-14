#!/usr/bin/env python3
"""Source-selected flag repair and independent byte/address writer interface.

The positive 1F/14 path is a CONDITIONAL PRIMARY ROM contract, not a
keyboard or Ms-byte supplier. Original66 constructs67; no return or IP
is injected into the reference. A marker exit is an explicit assumption.
Native C0/C1 controls are tested separately, including their failed gate.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, UGE

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-c9-page-island.py'))
r, w, q, states, edges = (source[n] for n in ('r', 'w', 'q', 'states', 'edges'))
walk = source['walk']


def preserving_clearers():
    # These are source-selected words, not three assumed native inlets.
    for code in (0x14, 0x29, 0x86):
        a = q['State'](f'writer_clear_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'writer_clear_keys_{code:02X}'),
                    emitted_outputs=out)
        w['prove'](p, And(w['ip'](b) == 0xD3, b.r[26] == 0,
            *[b.r[j] == a.r[j] for j in (2, 23, 30, 31, 33, 34)],
            w['eq'](out, a.m)),
            f'{code:02X} clears R26 but holds input byte, PC, mode and R23; no ring write')
    # 86 itself holds the address. Its only original caller does NOT.
    parents = Counter(states[i][0] for i, row in enumerate(edges)
        for child in row if states[child][0] == 0x86)
    assert parents == {0x74: 492}
    a = q['State']('writer_address_74'); p = w['base'](a, 0x74); out = []
    b = w['ex'](a, 0x74, *q['arbitrary_keys']('writer_address_74_keys'), emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0x86, b.r[31] == a.r[30], b.r[34] == a.r[33],
        b.r[30] == a.r[30], b.r[33] == a.r[33], b.r[23] == a.r[23],
        w['eq'](out, a.m)),
        'original74 couples destination PC to the incoming byte BEFORE clearer86')
    assert Counter(states[i][0] for i, row in enumerate(edges)
        for child in row if states[child][0] == 0x14) == {0x1F: 56}
    print('PASS original86 caller74 is address-coupled; 1F/14 may preserve '
          'independent byte/address, but a genuine joint inlet is still missing.', flush=True)


def independent_writer_interface():
    # Programme addresses84..90 are decimal BCD, not a binary84..90.
    # All256 incoming bytes, all other data and all future key pins are free.
    for offset in range(7):
        label = f'writer_interface_{offset}'
        a = q['State'](label); p = w['base'](a, 0x1F)
        address = 84+offset
        p.add(a.s1 == 4, UGE(a.r[2], 5), a.r[23] != 0,
              a.r[31] == address % 10, a.r[34] == address // 10)
        prefix = (0x1F, 0x14, 0xD3, 0x63, *([0x64]*13), 0x66)
        b = walk(a, p, prefix, label+'_normalizer')
        w['prove'](p, And(w['ip'](b) == 1, w['stack'](b)[0] == 0x67,
            b.r[32] == 12, b.r[35] == offset, b.s1 == 9, b.r[26] == 0,
            *[b.r[j] == a.r[j] for j in (2, 23, 30, 31, 33, 34)]),
            f'CONDITIONAL offset{offset}: original1F/14/D3/63/64x13/66 '
            'creates67, preserves independent byte/address, clears R26')
        # A real source exit from01, NOT a forced safe physical address.
        # Prior wait induction covers any finite number of leading01 waits.
        p.add(b.m[22] == 15)
        b = walk(b, p, (1, *([2]*13), 3, 4, 0xBA, 0xCC, 0xCD), label+'_wait')
        w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
            b.r[29] == 0, b.r[38] == 8, b.r[35] == offset, b.r[32] == 12,
            b.s1 == 9, b.r[26] == 0, UGE(b.r[2], 5), b.r[23] == a.r[23],
            b.r[30] == a.r[30], b.r[33] == a.r[33]),
            f'CONDITIONAL offset{offset}: exact original writer-C9 interface; '
            'Ms-byte supplier, nonzero input flag and physical page NOT constructed')
    print('PASS seven nonempty independent-byte/address contracts, all256 source '
          'bytes each. The interface meets the proved C9/67 writer contract. '
          'This is PRIMARY control/data composition, NOT a native key recipe, '
          'physical Ms transfer or partialK2.', flush=True)


def nop_flag_barrier():
    # 54 is reached in the fixed native operand controls. These statements
    # do not assert that every possible path to14 traverses54/58.
    for code in (0x54,):
        a = q['State'](f'nop_flag_clear_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'nop_flag_clear_keys_{code:02X}'))
        w['prove'](p, b.r[23] == 0, f'original{code:02X} clears R23, regardless of numeric ST1[7]')
    # The actual suffix from58 to the FIRST D3 has no full91. Its waits
    # hold R23 too, so arbitrary keyboard timing does not import ST1[7].
    holding = (0x58, 0x4E, 0x97, 0x99, 0x9B, 0x9C, 0x9E, 0x9F, 0xAA,
               0xE5, 0xE6, 0xED, 0xEE, 0xAB, 0xAD, 0xA5, 0x1F, 0x14, 0xD3)
    for code in holding:
        a = q['State'](f'nop_flag_hold_{code:02X}'); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](f'nop_flag_hold_keys_{code:02X}'))
        w['prove'](p, b.r[23] == a.r[23], f'{code:02X} holds R23 before the first NOP gate', False)
    a = q['State']('nop_zero_D3'); p = w['base'](a, 0xD3); p.add(a.r[23] == 0)
    b = w['ex'](a, 0xD3, *q['arbitrary_keys']('nop_zero_D3_keys'))
    w['prove'](p, w['ip'](b) == 0xD5,
        'R23zero forces D3→D5, not writer normalizer63, independent of byte/PC/mode/keys')
    print('PASS C1 in numeric ST1[7] is not a pre-gate flag repair on the '
          'observed NOP suffix. Later full91 can import it, but is too late '
          'for this first D3. Other real inlets remain open.', flush=True)


def late_joint_return():
    # A source-directed number1.0000005 supplies ST1[0]=5/[7]=1/[8]=0.
    # Native evidence supplies this actual numeric buffer. The universal
    # contract still does NOT grant a different return, PC or Ms source.
    double = runpy.run_path(str(root / 'cache-cf-ready-control.py'))['double']
    a = q['State']('late_joint_original_E3'); p = w['base'](a, 0xE3)
    p.add(a.st[1] == 5, a.st[22] == 1, a.st[25] == 0)
    out = []; b = w['ex'](a, 0xE3, *q['arbitrary_keys']('late_joint_original_E3_keys'),
                         emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0x91, w['stack'](b)[0] == 0xE4,
        w['eq'](b.r[0:36:3], a.r[0:36:3]), w['eq'](b.st[1:36:3], a.st[1:36:3]),
        w['eq'](out, a.m)),
        'originalE3 calls91 with E4; input A12 and numeric ST1 held')
    b = walk(b, p, double, 'late_joint_original91')
    w['prove'](p, And(w['ip'](b) == 0xE4, b.r[2] == 5, b.r[23] == 1, b.r[26] == 0,
        w['eq'](b.r[0:36:3], a.r[0:36:3])),
        'originalE3/full91/E4 imports the joint writer fields5/1/0; A12 held')
    for code in (0xE4, 0xDE, 0xDF):
        a = q['State'](f'late_joint_exit_{code:02X}'); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](f'late_joint_exit_keys_{code:02X}'),
                    emitted_outputs=out)
        if code == 0xE4:
            claim = And(w['ip'](b) == 0xDE,
                b.r[31] == a.r[30], b.r[34] == a.r[33],
                *[b.r[j] == a.r[j] for j in (2, 23, 26, 30, 33)])
        elif code == 0xDE:
            claim = And(w['ip'](b) == (q['BitVecVal'](0xD0, 8) | q['ZeroExt'](4, a.r[34])),
                b.r[23] == 7, b.r[26] == 0, b.r[2] == a.r[2],
                b.r[30] == a.r[31], b.r[33] == 15,
                b.r[31] == a.r[31], b.r[34] == a.r[34])
        else:
            claim = And(w['ip'](b) == 0x88, b.r[2] == 0, b.r[23] == 7, b.r[26] == 0,
                *[b.r[j] == a.r[j] for j in (30, 31, 33, 34)])
        descriptions = {0xE4: 'couples PC to byte and forces DE',
            0xDE: 'replaces byte high tetra with F/sets R23seven; dispatch D0|PC-high',
            0xDF: 'holds byte/PC but sets mode0/R23seven/R26zero and forces88'}
        w['prove'](p, And(claim, w['eq'](out, a.m)),
            'original'+f'{code:02X} '+descriptions[code])
    print('PASS native joint5/1/0 is at ORIGINAL E4, not a free BE/14 return. '
          'E4/DE couples the destination and changes the byte; actual60h goes '
          'to D6 with F0h. Other DE types/exits need their own source/inlet proof.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    preserving_clearers()
    independent_writer_interface()
    nop_flag_barrier()
    late_joint_return()
    r['inlet']['immutable_reference']()
