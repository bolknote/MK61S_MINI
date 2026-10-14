#!/usr/bin/env python3
"""Exact selected A3/BB caller contract, not a native keyboard witness.

The COMPLETE reset graph gives the sole A3->BB source and its real
93/E5/AD return context. A14/21 source induction binds the data to the
diagonal vector; no free49, FA header or byte source is imported from the
different48 caller. Arbitrary serial inputs overapproximate the ring.
Original A3 and BC writes are exposed, never treated as memory-neutral.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, Or, UGE, ULE, sat

root = Path(__file__).resolve().parent
basis = runpy.run_path(str(root / 'cache-bc-zero07-native-cut.py'))
r, w, q, states, edges, execute = (basis[n] for n in
    ('r', 'w', 'q', 'states', 'edges', 'execute'))
A = lambda a: a.r[0:36:3]
B = lambda a: a.r[1:36:3]
C = lambda a: a.r[2:36:3]


def eq(xs, ys):
    assert len(xs) == len(ys), (len(xs), len(ys))
    return w['eq'](xs, ys)


def selected_a3_source_cut():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    targets = {i for i, a in enumerate(states) if a[0] == 0xA3
               and any(states[j][0] == 0xBB for j in edges[i])}
    earlier = {i for i, a in enumerate(states) if a[0] == 0xA3
               and any(states[j][0] == 0x55 for j in edges[i])}
    assert len(targets) == 1 and targets == earlier
    for i in targets:
        assert states[i][1:4] == [[0x93, 0xE5, 0xAD], 'diagonal', [9]]
        assert states[i][7] == [0]
        assert {states[j][0] for j in edges[i]} == set(range(0, 256, 17))
    region = basis['backward'](targets, {0xA9})
    counts = Counter(states[i][0] for i in region)
    pairs = basis['internal_pairs'](region)
    assert len(region) == 14 and sum(pairs.values()) == 21
    assert basis['external_pairs'](region) == {(0xAD, 0xA9): 2}
    assert not region & set(graph['indexes']['roots'])
    # Reuse the verified SAME-class relation, not a numerical coincidence
    # of a different A3 caller. Both original93/94 are expanded by execute.
    basis['a3_diagonal_provenance']()
    print('PASS COMPLETE sole A3->BB is the SAME selected14/21 source '
          'as A3->55; head93/E5/AD, S1nine, counterzero. '
          'Graph coverage is NOT a positive native witness.', flush=True)
    return counts, pairs


def selected_data_provenance(counts, pairs):
    a = q['State']('a3bb_actual_AD_to_A9'); p = w['base'](a, 0xAD)
    b = execute(a, p, 0xAD, 'a3bb_actual_AD_to_A9')
    w['prove'](p, If(w['ip'](b) == 0xA9, b.r[26] == 0, True),
        'ALL ORIGINAL AD->A9 initializes C8/R26zero')

    def invariant(a, code):
        if code in (0xA9, 0x93, 0x95, 0x98, 0x9A): return a.r[26] == 0
        if code == 0xA2: return And(a.r[25] == 0, a.r[32] == 2)
        if code == 0xA3: return And(a.r[25] == 0, Or(a.r[32] == 2, a.r[32] == 3))
        return a.r[25] == 0

    for code in sorted(counts):
        label = f'a3bb_zero_b8_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        if code == 0xA9: p.add(w['stack'](a)[0] == 0x93)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[If(w['ip'](b) == dst, invariant(b, dst), True)
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves selected14/21 zero-B8/type provenance')
    print('PASS GLOBAL selected A3 also has B8/R25zero and TYPE2/3. Zero is imported '
          'by original9A from AD-initialized C8, and preserved through '
          'all selected AD/A2/E5 loops. AD->A3 givesTYPE3; AD->A2/'
          'A2->A3 givesTYPE2. Not an arbitrary B12/C12 payload.', flush=True)


def source_packet(a):
    return And(basis['correlation'](a), a.r[37] == 11,
        a.r[25] == 0, a.r[26] == 0, a.s1 == 9, Or(a.r[32] == 2, a.r[32] == 3),
        *[w['stack'](a)[j] == value for j, value in enumerate((0x93, 0xE5, 0xAD))])


def original_step(a, p, code, label):
    w['prove'](p, w['ip'](a) == code, label+' actual ORIGINAL IP', False)
    out = []
    b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'), emitted_outputs=out)
    return b, out


def direct_a3_bb_bc_contract():
    a = q['State']('a3bb_direct_packet'); p = w['base'](a, 0xA3)
    p.add(source_packet(a)); assert p.check() == sat
    b, out = original_step(a, p, 0xA3, 'a3bb_A3')
    w['prove'](p, And(w['ip'](b) == 0xBB, b.r[37] == 3, b.r[40] == 10,
        b.s1 == 10, eq(A(b), A(a)), eq(B(b), B(a)), eq(C(b), C(a)),
        eq(b.st, a.st),
        eq([out[j] for j in (28, 31, 34)], A(a)[9:12]),
        *[out[j] == a.m[j] for j in range(42) if j not in (28, 31, 34)]),
        'ORIGINAL A3->BB: vectorBB exchanged with IPA3, tailA3 NOT FA; '
        'S1nine->A; three upper M2 tetras written from A9/A10/A11')
    before = b; b, out = original_step(b, p, 0xBB, 'a3bb_BB')
    rotated = [*B(a)[1:], q['N4'](3), q['N4'](10), B(a)[0]]
    w['prove'](p, And(w['ip'](b) == 0xBC,
        eq(b.r[1:42:3], rotated), eq(A(b), A(a)), eq(C(b), C(a)),
        eq(b.st, a.st), eq(out, before.m), b.s1 == 10, b.s == B(a)[0],
        w['byte'](b.r[31], b.r[34]) == 0x3B, b.r[22] == 0),
        'ORIGINAL BB rotates actual B14 with A3 tail: numeric byte3B, '
        'not FB/F0..FF; B7zero, no ring write')
    before = b; b, out = original_step(b, p, 0xBC, 'a3bb_BC')
    payload = [*B(a), q['N4'](3), q['N4'](10)]
    w['prove'](p, And(w['ip'](b) == 0x93,
        eq(w['stack'](b), [q['BitVecVal'](v, 8) for v in (0xE5, 0xAD, 0x93)]),
        eq([out[1+3*j] for j in range(14)], payload),
        *[out[j] == before.m[j] for j in range(42) if j % 3 != 1],
        eq(A(b), A(a)), eq(B(b), rotated[:12]), eq(C(b), C(a)),
        eq(b.st[:36], a.st[:36]), b.s1 == 10),
        'ORIGINAL BC writes B0..B11,3,A into14 M2 positions; '
        'fixed B8=0/B10=9/B11=B, true return93, NOT49')
    for code in (0x93, 0x94, 0x95, 0x98, 0x9A):
        before = b; b, out = original_step(b, p, code, f'a3bb_return_{code:02X}')
        w['prove'](p, eq(out, before.m),
            f'ORIGINAL{code:02X} true93 return path has no ring write', False)
    w['prove'](p, And(w['ip'](b) == 0xE5, b.s1 == 10,
        eq(A(b), rotated[:12]), eq(B(b), C(a)), eq(C(b), a.st[0:36:3]),
        eq(w['stack'](b), [q['BitVecVal'](v, 8) for v in (0xAD, 0x93, 0xE5)])),
        'TRUE93/94/95/98/9A return reaches E5/S1A with A=B1..B11,3; '
        'no IMMEDIATE49/BD/BE or imported arbitrary-byte writer continuation')
    # PRIMARY marker hypothesis, not a write to a native calculator. The
    # wait lemma below handles arbitrary finite nonmarker repetitions.
    p.add(b.m[22] == 15)
    before = b; b, out = original_step(b, p, 0xE5, 'a3bb_marker_exit')
    w['prove'](p, And(w['ip'](b) == 0xE6, b.s1 == 10, eq(A(b), rotated[:12]),
        eq(out, before.m)), 'CONDITIONAL real marker lets E5 leave for E6/S1A')
    before = b; b, out = original_step(b, p, 0xE6, 'a3bb_E6')
    w['prove'](p, And(w['ip'](b) == 0xEA, b.s1 == 10, eq(A(b), rotated[:12]),
        eq(out, before.m)),
        'ORIGINAL E6/S1A selects EA, NEVER E9 store or E7 exchange')
    before = b; b, out = original_step(b, p, 0xEA, 'a3bb_actual_EA_dispatch')
    w['prove'](p, And(w['ip'](b) == If(UGE(a.r[35], 10),
        q['BitVecVal'](0xD8, 8), q['BitVecVal'](0xEC, 8)), eq(out, before.m)),
        'SELECTED A3 true-return EA: incoming KIND0..9 selectsEC, '
        'KIND A..F selectsD8; TYPE2/3 excludes the other9/zero exception')
    print('PASS CONDITIONAL direct A3/BB/BC writer and its TRUE return. '
          'NOT an arbitrary byte/word exchange: fixed3B, five fixed M2 '
          'tetras, preliminary A3 write and later EA branch. '
          'Native joint construction, physical word/phase, displaced-word '
          'backup, universal EA exit and inverse remain unproved.', flush=True)


def actual_ea_branch_gates():
    a = q['State']('a3bb_EA_local'); p = w['base'](a, 0xEA)
    b, out = original_step(a, p, 0xEA, 'a3bb_EA_local')
    d8 = Or(UGE(a.r[34], 10),
            And(a.r[34] == 9, a.r[28] == 0, a.r[31] == 0))
    w['prove'](p, And(Or(w['ip'](b) == 0xD8, w['ip'](b) == 0xEC),
        (w['ip'](b) == 0xD8) == d8,
        w['stack'](b)[0] == 0xEB,
        eq(w['stack'](b)[1:], w['stack'](a)[:2]),
        b.r[37] == 6, b.r[40] == 12,
        eq(B(b), B(a)), eq(out, a.m)),
        'ALL ORIGINAL EA uses B order/type for D8 versus EC; '
        'constructs true returnEB/vectorC6 and writes no ring tetras')
    a = q['State']('a3bb_EC_local'); p = w['base'](a, 0xEC)
    b, out = original_step(a, p, 0xEC, 'a3bb_EC_local')
    w['prove'](p, And(w['ip'](b) == 0x40,
        eq(A(b), B(a)), eq(B(b), A(a)), b.r[37] == 14, b.r[40] == 3,
        eq(out, a.m)),
        'ALL ORIGINAL EC exchanges A/B and enters40; it is NOT '
        'a return to E9 or a memory-neutral finished calculator exit')


def conditional_formatter_return():
    # A second component path, not a constructor for its native A3 packet.
    # EA sees original C in B after the real93 return. A low C11 and
    # nonzero C7 select EC and the unshifted formatter path respectively.
    label = 'a3bb_conditional_formatter'
    a = q['State'](label); p = w['base'](a, 0xA3)
    p.add(source_packet(a), ULE(a.r[35], 9), a.r[23] != 0)
    sequence = (0xA3, 0xBB, 0xBC, 0x93, 0x94, 0x95, 0x98, 0x9A,
        0xE5, 0xE6, 0xEA, 0xEC, 0x40, 0x41, 0x42, 0x46,
        0xE5, 0xE6, 0xE8, 0xE7, 0x47, 0x49, 0xBD,
        *basis['old']['inlet']['double'])
    b = a
    for index, code in enumerate(sequence):
        if code == 0xE5: p.add(b.m[22] == 15)
        before = b
        b, out = original_step(b, p, code, label+f'_{index}_{code:02X}')
        if code == 0xEA:
            w['prove'](p, And(w['ip'](b) == 0xEC,
                b.r[24] == If(a.r[28] == 0, q['N4'](15), q['N4'](1)),
                eq(A(b)[9:12], [q['N4'](9), q['N4'](11), q['N4'](3)])),
                'A3 true-return EA/low-C11: EC selected; saved B9 becomes '
                'F or1 in A8, upper9/B/3 held')
        elif code in (0xEC, 0x40):
            w['prove'](p, eq(A(b), C(a)),
                f'ORIGINAL{code:02X} exposes original A3-entry C12, NOT its cached A12')
        elif code == 0xE7:
            w['prove'](p, And(w['ip'](b) == 0x47,
                eq([out[1+3*j] for j in range(12)], C(a)),
                eq(A(b), before.m[1:36:3]),
                *[out[j] == before.m[j] for j in range(42) if j % 3 != 1 or j >= 37]),
                'CONDITIONAL original E7 exchanges C12 with numeric M2, '
                'writes no other lane/tail and returns true47')
        elif code == 0x47:
            w['prove'](p, And(w['ip'](b) == 0x49, eq(A(b), C(a))),
                'TRUE47 overwrites displaced M2 in A with saved sourceC12; '
                'later49 is real, but NOT the immediate BC return')
        if code not in (0xA3, 0xBC, 0xE7):
            w['prove'](p, eq(out, before.m),
                f'conditional formatter ORIGINAL{code:02X} has no ring write', False)
    w['prove'](p, And(w['ip'](b) == 0xBE,
        eq(A(b)[9:12], [q['N4'](9), q['N4'](11), q['N4'](3)]),
        w['byte'](b.r[30], b.r[33]) == 0x3B),
        'CONDITIONAL E7/47/49/BD/full91 really reaches BE, '
        'but its possible writer source byte is STILL3B, not arbitrary')
    print('PASS second CONDITIONAL A3/BB true-return family: '
          'low C11=0..9/nonzero C7 ->EA/EC/40/41/42/46/'
          'E5/E6/E8/E7/47/49/BD/full91/BE. '
          'There ARE later real49/BE entries, only after another M2 '
          'exchange whose displaced data47 discards. Fixed3B survives. '
          'No native packet, physical Ms source/phase, backup, '
          'C9/F9 continuation or inverse is established.', flush=True)


def true_return_marker_wait():
    a = q['State']('a3bb_true_wait'); p = w['base'](a, 0xE5)
    p.add(a.s1 == 10, w['stack'](a)[0] == 0xAD)
    b, out = original_step(a, p, 0xE5, 'a3bb_true_wait')
    w['prove'](p, And(w['ip'](b) == If(a.m[22] == 15,
        q['BitVecVal'](0xE6, 8), q['BitVecVal'](0xE5, 8)),
        b.s1 == 10, eq(w['stack'](b), w['stack'](a)),
        eq(A(b), A(a)), eq(B(b), B(a)), eq(C(b), C(a)),
        eq(b.st[:36], a.st[:36]), eq(out, a.m)),
        'ALL ORIGINAL E5/S1A waits preserve packet for ANY finite repeat count')


def displaced_word_not_read():
    a = q['State']('a3bb_no_displaced_read'); p = w['base'](a, 0xBC)
    other = q['State']('a3bb_other_M2'); b = a.copy()
    for j in range(1, 42, 3): b.m[j] = other.m[j]
    keys = q['arbitrary_keys']('a3bb_no_displaced_read_keys')
    serial = q['State']('a3bb_no_displaced_read_serial').m
    oa, ob = [], []
    aa = w['ex'](a, 0xBC, *keys, serial_inputs=serial, emitted_outputs=oa)
    bb = w['ex'](b, 0xBC, *keys, serial_inputs=serial, emitted_outputs=ob)
    w['prove'](p, And(w['same'](aa, bb), eq(oa, ob)),
        'ALL ORIGINAL BC: displaced14 M2 tetras have NO surviving '
        'primary/outgoing copy; an earlier independent backup is required')

    # The formatter branch above constructs47 with ORIGINAL46. Recheck
    # the whole-state loss lemma for that return, not just the visible A.
    a = q['State']('a3bb_E7_displaced_loss'); p = w['base'](a, 0xE7)
    p.add(w['stack'](a)[0] == 0x47)
    other = q['State']('a3bb_E7_other_M2'); b = a.copy()
    for j in range(1, 36, 3): b.m[j] = other.m[j]
    keys = q['arbitrary_keys']('a3bb_E7_displaced_loss_keys')
    serial = q['State']('a3bb_E7_displaced_loss_serial').m
    oa, ob = [], []
    aa = w['ex'](a, 0xE7, *keys, serial_inputs=serial, emitted_outputs=oa)
    bb = w['ex'](b, 0xE7, *keys, serial_inputs=serial, emitted_outputs=ob)
    w['prove'](p, And(w['ip'](aa) == 0x47, w['ip'](bb) == 0x47, eq(oa, ob)),
        'E7/true47 reads displaced numericM2, but emits only the same source')
    keys = q['arbitrary_keys']('a3bb_47_displaced_loss_keys')
    serial = q['State']('a3bb_47_displaced_loss_serial').m
    oa, ob = [], []
    aa = w['ex'](aa, 0x47, *keys, serial_inputs=serial, emitted_outputs=oa)
    bb = w['ex'](bb, 0x47, *keys, serial_inputs=serial, emitted_outputs=ob)
    w['prove'](p, And(w['same'](aa, bb), eq(oa, ob)),
        'ALL ORIGINAL E7/true47: arbitrary displaced numericM2 differences '
        'vanish from WHOLE primary/outgoing state; independent backups not excluded')


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    counts, pairs = selected_a3_source_cut()
    selected_data_provenance(counts, pairs)
    direct_a3_bb_bc_contract()
    actual_ea_branch_gates()
    conditional_formatter_return()
    true_return_marker_wait()
    displaced_word_not_read()
    r['inlet']['immutable_reference']()
    print('PASS source-driven A3 direct writer audit. No key search, '
          'native/live/ALL5 experiment, reference/state/IP/return repair '
          'or general partialK2 impossibility claim.', flush=True)
