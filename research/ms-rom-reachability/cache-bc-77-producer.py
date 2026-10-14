#!/usr/bin/env python3
"""Original1D/25 resolver constructs a high77 inlet and an aligned M1 backup.

Graph classes are overapproximations, not native witnesses. Positive paths
below are conditional PRIMARY contracts. R26=8 chooses original25, whose
own marker/counter call constructs26; DD makes selectorC from A0=B, and
counter typeB supplies operandC. No return/IP is invented. This component
contract does NOT prove a native joint producer/Ms source/physical exchange.

LATER AUDIT: cache-bc-77-parity.py proves that this native high C inlet
is impossible: R26eight1D types are even; ALL nonzero25/kind7 types are
even and the original counter makes an ODD operand at selectorC77. These
positive PRIMARY contracts remain valid outside reset reachability, not
an open native producer candidate. The other8B/limitedBB paths are separate.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, If, Or, UGE, sat

root = Path(__file__).resolve().parent
prior = runpy.run_path(str(root / 'cache-bc-60-inlet.py'))
r, w, q = (prior[n] for n in ('r', 'w', 'q'))
states, edges = prior['states'], prior['edges']
walk, double = prior['walk'], prior['double']
A, B, ST0, ST1 = (prior[n] for n in ('A', 'B', 'ST0', 'ST1'))
N8 = prior['N8']


def original_77_source_cut():
    parents = Counter(states[i][0] for i, row in enumerate(edges)
        for child in row if states[child][0] == 0x77)
    assert parents == {0x7C: 266, 0x7E: 98, 0xE7: 6, 0xE9: 3, 0xEE: 6, 0xA3: 1}
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    wanted = {i for i, a in enumerate(states) if a[0] == 0x77 and
        (a[5] is None or 12 in a[5]) and (a[7] is None or any(n != 0 for n in a[7]))}
    assert sum(a[0] == 0x77 for a in states) == 165 and len(wanted) == 24
    assert all(states[i][1][0] == 0x29 and states[i][2] == 0x6C and states[i][3] == [14]
               for i in wanted)
    filtered = Counter(states[i][0] for i, row in enumerate(edges) for child in row if child in wanted)
    assert filtered == {0x7E: 24}
    # This absence uses audited COMPLETE coverage. The remaining24 are
    # deliberately NOT called reachable high-type states or key sequences.
    for code in (0x7C, 0x7E):
        label = f'bc77_source_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        if code == 0x7C:
            claim = b.r[38] == 8
        else:
            claim = And(w['ip'](b) == (N8(0x70) | q['ZeroExt'](4, a.r[35])),
                ((w['ip'](b) == 0x77) == (a.r[35] == 7)),
                *[b.r[j] == a.r[j] for j in (26, 29, 32, 35, 38)])
        w['prove'](p, claim, f'original{code:02X} exact pointer/kind cut')
    for target, previous in ((0x26, 0xD4), (0x28, 0x26), (0x7E, 0x28)):
        ids = {i for i, a in enumerate(states) if a[0] == target and
            (a[5] is None or 12 in a[5]) and (a[7] is None or any(n != 0 for n in a[7]))}
        incoming = Counter(states[i][0] for i, row in enumerate(edges) for child in row if child in ids)
        assert len(ids) == 24
        assert incoming == ({0x28: 24, 0x7E: 24} if target == 0x7E else {previous: 24})
    print('PASS COMPLETE77 source cut:165 classes;24 allow selectorC/nonzeroR26, '
          'all from7E/kind7 via D4/26/28. Other five direct parents are excluded '
          'for this inlet. The24 classes are candidates, NOT native witnesses.', flush=True)


def original_resolver_gates():
    a = q['State']('bc77_exact_1D'); p = w['base'](a, 0x1D)
    b = w['ex'](a, 0x1D, *q['arbitrary_keys']('bc77_exact_1D_keys'))
    w['prove'](p, And(w['ip'](b) == If(UGE(a.r[26], 3),
        N8(0x1D)+q['ZeroExt'](4, a.r[26]), If(a.r[26] == 2, N8(0x2F), N8(0x2E))),
        ((w['ip'](b) == 0x25) == (a.r[26] == 8)),
        *[b.r[j] == a.r[j] for j in (26, 29, 32, 35, 38)], w['eq'](A(b), A(a))),
        'original1D selects25 IFF R26eight; holds type/kind/operand/pointer/A12')
    a = q['State']('bc77_exact_25'); p = w['base'](a, 0x25)
    b = w['ex'](a, 0x25, *q['arbitrary_keys']('bc77_exact_25_keys'))
    w['prove'](p, And(w['ip'](b) == 1, w['stack'](b)[0] == 0x26, b.s1 == 4,
        *[b.r[j] == a.r[j] for j in (26, 29, 32, 35, 38)],
        w['eq'](A(b), A(a)), w['eq'](B(b), B(a))),
        'original25 creates26/S1four, not a free resolver return')


def original_high_1D_cut():
    # R26eight candidates use60/18/1B. The abstractions do NOT prove that
    # their type/kind/A payload constraints can coexist in a native state.
    ids = {i for i, a in enumerate(states) if a[0] == 0x1D and
        (a[7] is None or 8 in a[7])}
    assert sum(a[0] == 0x1D for a in states) == 119 and len(ids) == 4
    assert all(states[i][1][0] == 0x6E and states[i][2] == 0x5E and
        states[i][3] == [0] and states[i][5] == [9] for i in ids)
    for target, previous in ((0x1D, 0x1B), (0x1B, 0x18), (0x18, 0x60)):
        assert all(states[i][0] == target for i in ids)
        incoming = {i for i, row in enumerate(edges) if any(child in ids for child in row)}
        assert len(incoming) == 4 and all(states[i][0] == previous for i in incoming)
        ids = incoming

    a = q['State']('bc77_upstream60'); p = w['base'](a, 0x60)
    p.add(a.r[38] == 9, a.r[25] == a.r[31])
    b = walk(a, p, (0x60, 0x18, 0x1B), 'bc77_upstream60')
    w['prove'](p, And(w['ip'](b) == 0x1D, b.r[32] == a.r[32]+2,
        *[b.r[j] == a.r[j] for j in (26, 29, 35, 38)],
        w['eq'](A(b), [*A(a)[1:], A(a)[0]]), w['eq'](B(b), B(a)),
        w['eq'](ST0(b), ST0(a)), w['eq'](ST1(b), ST1(a))),
        'original60/selector9/18/1B construct type+2 at1D; type9 needed forB')

    # Recheck the previously proved reset invariant, then use it on this
    # particular downstream entry, without bounding marker/key waiting.
    prior['low_type_reset_cut']()
    a = q['State']('bc77_standard07'); p = w['base'](a, 7)
    p.add(Or(a.r[32] == 0, a.r[38] == 8), a.r[26] == 8)
    b = walk(a, p, (7,), 'bc77_standard07')
    p.add(w['ip'](b) == 0x6D)  # restrict the actual07 branch, never set its IP
    b = walk(b, p, (0x6D, 0x60), 'bc77_standard07_call')
    p.add(w['ip'](b) == 0x18)
    b = walk(b, p, (0x18, 0x1B), 'bc77_standard07_decode')
    w['prove'](p, And(w['ip'](b) == 0x1D, b.r[32] == 2, b.r[26] == 8),
        'ALL standard reset07/6D/60/18/1B reach1D only withtype2, never requiredB')
    print('PASS COMPLETE1D R26eight cut:4/119 candidate classes, selector9/S1zero/'
          'head6E/vector5E, all via60/18/1B; '
          'source selector9/equality makes type+2. Standard07 parent gives2, '
          'notB. High77 parent preparation is still missing, not a key witness.', flush=True)


def resolver_prefix(a, p, label):
    before = a
    b = walk(a, p, (0x1D, 0x25), label+'_call')
    p.add(b.m[22] == 15)  # explicit physical marker assumption in PRIMARY proof
    b = walk(b, p, (1, *([2]*12), 3, 4, 0xBA, 0xCB, 0xDD), label+'_wait')
    w['prove'](p, And(w['ip'](b) == 0xD4, b.r[29] == 12, b.r[32] == 11,
        b.r[35] == 7, b.r[38] == 12, w['stack'](b)[0] == 0x26,
        w['eq'](A(b), [*A(before)[1:], A(before)[0]])),
        label+' original counter12/selectorC/high-typeB constructor beforeD4')
    d4_input = b
    out = []; b = w['ex'](b, 0xD4, *q['arbitrary_keys'](label+'_D4_keys'),
        serial_inputs=q['State'](label+'_D4_serial').m, emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0x26,
        w['eq'](out[0:36:3], A(before)),
        *[out[j] == d4_input.m[j] for j in range(42) if j % 3 != 0 or j >= 36]),
        label+' D4 writes ALL12 originalA ALIGNED to numericalM1 and returns ORIGINAL26')
    b = walk(b, p, (0x26, 0x28, 0x7E), label+'_kind7')
    w['prove'](p, And(w['ip'](b) == 0x77, b.r[26] == 8,
        b.r[29] == 12, b.r[32] == 11, b.r[35] == 7, b.r[38] == 12,
        w['eq'](A(b), [*A(before)[2:], *A(before)[:2]]),
        w['eq'](B(b), B(before)), w['eq'](ST0(b), ST0(before)), w['eq'](ST1(b), ST1(before))),
        label+' joint77 constructor: typeB/numberC/kind7/pointerC; all B12/ST0/ST1 held')
    return b


def upstream_writer_families():
    for address in (*range(84, 91), 99):
        label = f'bc77_resolver_writer_address{address}_C'
        writer_counter = address//7+1
        a = q['State'](label); p = w['base'](a, 0x1D)
        p.add(a.r[0] == 11, a.r[26] == 8, a.r[32] == 11, a.r[35] == 7,
            a.r[25] == a.r[31], a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
            a.st[30] == address % 10, a.st[33] == address // 10)
        b = resolver_prefix(a, p, label)
        b = walk(b, p, (0x77, 0x6D, 0x60, 0x48, 0xB1, 0xB3, 0xBC, 0x49, 0xBD,
            *double, 0xBE, 0x63, *([0x64]*writer_counter), 0x66), label, only_ring_writer=0xBC)
        p.add(b.m[22] == 15)
        b = walk(b, p, (1, *([2]*writer_counter), 3, 4, 0xBA, 0xCC, 0xCD), label+'_writerwait')
        w['prove'](p, And(w['ip'](b) == 0xC9, w['stack'](b)[0] == 0x67,
            w['eq'](A(b), B(a)), w['eq'](ST0(b)[:9], A(a)[3:12]),
            w['eq'](ST1(b)[9:12], A(a)[:3]),
            w['eq']([b.st[j] for j in (28, 31, 0, 3, 9, 12)], [a.r[j] for j in w['raw']])),
            label+' three rotations, ALL12 originalA in split reserve + prior alignedM1 backup')
        p.push(); byte = q['BitVec'](label+'_all256_byte', 8)
        p.add(w['byte'](b.r[30], b.r[33]) == byte)
        assert p.check() == sat and q['possible_values'](byte, p, 257) == list(range(256)); p.pop()
    print('PASS eight CONDITIONAL original1D/25 resolver→77→BC→writer interfaces, '
          'all7 positions plus native-control99/all256 bytes. DD constructsC and counterB constructs '
          'numberC; D4 backs up ALL12 A toM1. Initial A0=B is a payload restriction, '
          'not arbitrary three-byte coverage. Native producer/pages/exit/exchange missing.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    original_77_source_cut()
    original_resolver_gates()
    original_high_1D_cut()
    upstream_writer_families()
    r['inlet']['immutable_reference']()
    print('PASS77 producer audit. No native high1D inlet, real Ms provenance, '
          'safe ordinary-register backup, exchange or partialK2.', flush=True)
