#!/usr/bin/env python3
"""ConstantCC A3 sources, earlier EE read and the real DD/DA writer.

COMPLETE source cuts prove the two constantCC A3 callers have KINDD,
TYPE2/3, S1nine, counter0 and B11six, unlike the diagonal CC caller.
Positive compositions are CONDITIONAL PRIMARY contracts, not native
key witnesses or physical Ms/PC writes. EE reads numericM2 before BC;
TYPE2/A2 waits retain its lower9, not all12. The DD return reaches DA.

TYPE2/A2 forces header3, not a two-sided exchange. TYPE3/header4 writes
six opaque tetras twice; the following real dispatch uses
RAW0. RAW0three reaches63; RAW0D loops atDD. A geometry-only ring audit
gives a necessary15-word timing condition, NOT a physical exchange proof.
No ROM/reference/state/IP/return repair, native/live/ALL5/key search.
"""
from collections import Counter, deque
from pathlib import Path
import runpy

from z3 import And, BitVecVal, If, Implies, Not, Or, UGE, sat, unsat

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-bc-direct-source-closure.py'))
diagonal = runpy.run_path(str(root / 'cache-bc-a3-direct-contract.py'))
r, w, q, basis, states, edges, pred, execute = (source[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred', 'execute'))
A, B, eq, checked = source['A'], source['B'], source['eq'], source['checked_dependency']
raw = (0, 3, 9, 12, 18, 21)
old_indices = (1, 2, 4, 5, 7, 8)
vector = lambda a: And(a.r[37] == 12, a.r[40] == 12)


def graph_check():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert graph['metadata']['stateFields'][4] == 'selectorMinusR35'
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    changed = [(i, j) for i, row in enumerate(edges) for j in row
               if states[j][2] == 0xCC and states[i][2] != 0xCC]
    assert len(changed) == 54
    assert Counter((states[i][0], states[j][0]) for i, j in changed) == {(0xE4, 0xDE): 54}
    checked('ALL three A3/CC sources, two constantCC plus SAME diagonal source',
            source['complete_writer_callers'])


def constant_cone(target):
    region, todo = {target}, deque([target])
    while todo:
        i = todo.popleft()
        if states[i][2] != 0xCC: continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    return region


def complete_constant_sources():
    graph_check()
    for head, target, ee_target, sizes, external in (
        (0x93, 11376, 9662, (21, 36, 17, 29), {(0x9A, 0xE4): 2}),
        (0xDD, 17324, 15270, (19, 30, 15, 23), {(0xE6, 0xE4): 4})):
        assert states[target][1:4] == [[head, 0xE5, 0xAD], 0xCC, [9]]
        full = constant_cone(target); upstream = constant_cone(ee_target)
        assert (len(full), sum(basis['internal_pairs'](full).values()),
                len(upstream), sum(basis['internal_pairs'](upstream).values())) == sizes
        assert basis['external_pairs'](full) == external
        assert basis['external_pairs'](upstream) == external
        assert not full & set(r['inlet']['g']['graph']['indexes']['roots'])
        assert all(states[i][0] == 0xE4 for i in full if states[i][2] != 0xCC)
        assert states[ee_target][1:5] == [[0xAD, head, 0xE5], 0xCC, [13], 0]
        pairs = basis['internal_pairs'](upstream)
        def inv(a, code):
            if code == 0xE4: return And()
            if code == 0xDE: return vector(a)
            if code in (0xD4, 0xD6):
                n = 4 if code == 0xD4 else 6
                return And(vector(a), a.r[26] == 0, a.r[34] == n, a.s1 == n)
            if code in (0xE5, 0xE6):
                return And(vector(a), a.r[26] == 0, Or(
                    And(a.r[34] == 4, a.s1 == 4),
                    And(a.r[34] == 6, a.s1 == a.r[35])))
            # Selected EE has S1=D and S1-KIND=0. Keep the implication
            # at generic ED/EE too, so other real S1 values are not hidden.
            return And(vector(a), a.r[26] == 0,
                Implies(a.s1 == 13, And(a.r[34] == 6, a.r[35] == 13)))
        for code in sorted({states[i][0] for i in upstream}):
            label = f'a3cc_header6_{head:02X}_{code:02X}'
            a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
            b = execute(a, p, code, label)
            destinations = sorted({d for c, d in pairs if c == code})
            w['prove'](p, And(*[Implies(w['ip'](b) == d, inv(b, d)) for d in destinations]),
                f'ALL ORIGINAL{code:02X} preserves COMPLETE{sizes[2]}/{sizes[3]} constantCC read6 source')

        tail = basis['backward']({target}, {0xEE}); pairs = basis['internal_pairs'](tail)
        assert len(tail) == 5 and sum(pairs.values()) == 7
        assert basis['external_pairs'](tail) == {(0xED, 0xEE): 1}
        def tail_inv(a, code):
            common = And(vector(a), a.r[26] == 0, a.r[34] == 6)
            if code == 0xEE:
                return And(common, a.s1 == 13, a.r[35] == 13,
                    *[w['stack'](a)[j] == v for j, v in enumerate((0xAD, head, 0xE5))])
            tags = And(*[w['stack'](a)[j] == v for j, v in enumerate((head, 0xE5, 0xAD))])
            if code == 0xAD:
                packet = Or(And(a.r[35] == 13, a.s1 == 13), And(a.r[32] == 13, a.s1 == 9))
            elif code == 0xA2: packet = And(a.r[32] == 2, a.r[35] == 13, a.s1 == 9)
            else:
                packet = And(Or(a.r[32] == 2, a.r[32] == 3), a.r[35] == 13, a.s1 == 9,
                    Implies(a.r[32] == 2, And(a.r[30] == 2, a.r[33] == 13)))
            return And(common, tags, packet)
        for code in sorted({states[i][0] for i in tail}):
            label = f'a3cc_tail_{head:02X}_{code:02X}'
            a = q['State'](label); p = w['base'](a, code); p.add(tail_inv(a, code))
            b = execute(a, p, code, label)
            destinations = sorted({d for c, d in pairs if c == code})
            w['prove'](p, And(*[Implies(w['ip'](b) == d, tail_inv(b, d)) for d in destinations]),
                f'ALL ORIGINAL{code:02X} preserves complete5/7 true-{head:02X} KINDD/TYPE2or3/B11six packet')
        print(f'PASS GLOBAL constantCC/head{head:02X}: TYPE2/3,KINDD,counter0,S1nine,B11=6. '
              f'FULL{sizes[0]}/{sizes[1]}, upstream{sizes[2]}/{sizes[3]}, tail5/7; '
              'not the diagonal B10nine/B11C packet or a native key witness.', flush=True)


def read_and_wait_contracts():
    for code in (0xEE, 0xA2):
        label = f'a3cc_read_wait_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'),
            serial_inputs=q['State'](label+'_serial').m, emitted_outputs=out)
        if code == 0xEE: data = eq(A(b), a.m[1:36:3])
        else:
            data = And(eq(A(b)[:10], A(a)[:10]), b.r[30] == a.r[32], b.r[33] == a.r[35],
                w['ip'](b) == If(a.m[22] == 15, BitVecVal(0xA3, 8), BitVecVal(0xA2, 8)))
        w['prove'](p, And(data, eq(B(b), B(a)), eq(b.st[:36], a.st[:36]), eq(out, a.m)),
            f'ORIGINAL{code:02X}: EE reads FULL12 M2; A2 holds lower10 but substitutes TYPE/KIND at A10/11')
    print('PASS early numericM2 read, and unlimited A2 waits preserve all six RAW '
          'positions1/2/4/5/7/8. A2 does NOT preserve all12 old EE tetras.', flush=True)


def restored_header_contract():
    a = q['State']('a3cc_9A_header'); p = w['base'](a, 0x9A)
    b = execute(a, p, 0x9A, 'a3cc_9A_header')
    w['prove'](p, And(b.r[26] == a.r[25], b.r[29] == a.r[28],
        b.r[32] == a.r[31], b.r[35] == a.r[34]),
        'ORIGINAL9A restores C8..11 from old B8..11; later TYPE/KIND are not an untouched opcode')


def step(a, p, code, label):
    w['prove'](p, w['ip'](a) == code, label+' actual original IP', False)
    out = []
    b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'),
        serial_inputs=q['State'](label+'_serial').m, emitted_outputs=out)
    return b, out


def e4_constructor(typ, waits, label):
    a = q['State'](label); p = w['base'](a, 0xE4)
    p.add(a.s1 == 4, a.r[35] == 13, a.r[32] == typ, a.r[26] == 0,
        a.r[37] == 8, a.r[40] == 13,
        *[w['stack'](a)[j] == v for j, v in enumerate((0xAD, 0xDD, 0xE5))])
    b = a; old_m2 = None
    sequence = (0xE4, 0xDE, 0xD6, 0xE5, 0xE6, 0xED, 0xEE, 0xAD, 0xAD)
    for i, code in enumerate(sequence):
        if code == 0xD6:
            p.add(w['ip'](b) == 0xD6); assert p.check() == sat
            w['prove'](p, a.r[33] == 6, label+' actual D6 choice constrains old E4 A11=6')
        if code == 0xE5: p.add(b.m[22] == 15)
        if code == 0xEE: old_m2 = b.m[1:36:3]
        before = b; b, out = step(b, p, code, label+f'_prefix{i}')
        w['prove'](p, eq(out, before.m), label+' original prefix does not write ring', False)
    assert old_m2 is not None
    if typ == 2:
        assert waits >= 1
        for i in range(waits):
            p.add(b.m[22] == 15 if i == waits-1 else b.m[22] != 15)
            before = b; b, out = step(b, p, 0xA2, label+f'_wait{i}')
            w['prove'](p, eq(out, before.m), label+' A2 wait is ring neutral', False)
    else: assert waits == 0
    w['prove'](p, And(w['ip'](b) == 0xA3, vector(b), b.r[35] == 13,
        b.r[32] == typ, b.s1 == 9, b.r[26] == 0,
        eq(B(b), A(a)), eq(A(b)[:10], old_m2[:10]),
        *[w['stack'](b)[j] == v for j, v in enumerate((0xDD, 0xE5, 0xAD))]),
        label+' E4/actualD6/EE/twoAD constructs BOTH old-source B12 and earlier-read M2 raw cache')
    return a, b, p, old_m2


def composed_dd_writer(typ, waits):
    label = f'a3cc_composed_type{typ}_wait{waits}'
    origin, a, p, old_m2 = e4_constructor(typ, waits, label)
    old_raw = [old_m2[j] for j in old_indices]; b = a
    for i, code in enumerate((0xA3, 0xCC, 0xBB, 0xBC, 0xDD, 0xDA)):
        before = b; b, out = step(b, p, code, label+f'_writer{i}')
        if code == 0xA3:
            w['prove'](p, eq(out[28:35:3], A(a)[9:]), label+' actual preliminary upper3 M2 write')
        elif code == 0xBC:
            w['prove'](p, And(eq(out[1:42:3], [*A(origin), q['N4'](3), q['N4'](10)]),
                eq(A(b)[:9], old_m2[:9]), w['ip'](b) == 0xDD, b.s1 == 10,
                w['byte'](b.r[31], b.r[34]) == 0x36),
                label+' real BC writes source E4 A12+tail3/A; keeps earlier-read RAW; true DD, byte36')
        else: w['prove'](p, eq(out, before.m), label+' no other prefix ring write', False)
    w['prove'](p, And(w['ip'](b) == 0xDC, Or(b.r[34] == 3, b.r[34] == 4),
        eq([b.r[j] for j in raw], old_raw)), label+' true DD/DA reaches DC with all six earlier EE raw tetras')
    if typ == 2:
        w['prove'](p, b.r[34] == 3,
            label+' TYPE2/A2 stamps A10=2/A11=D and forces DA header3; inverse stores are IMPOSSIBLE')
    # The first branch exits before either later M1 store.
    p.push(); p.add(b.r[34] == 3); z = b
    for i, code in enumerate((0xDC, 0xDE, 0xD3)):
        before = z; z, out = step(z, p, code, label+f'_header3_{i}')
        w['prove'](p, eq(out, before.m), label+' header3 exit has no further ring write', False)
    w['prove'](p, w['ip'](z) == 0x63, label+' header3 original D3 reaches63, not a fake49/76')
    p.pop()
    if typ == 2:
        print('PASS CONDITIONAL '+label+': complete source E4 word ->14 M2 and real63 exit. '
              'A2 keeps earlier EE RAW6, but header4/inverse M1 stores are excluded. '
              'No native/physical/safe full exchange claim.', flush=True)
        return
    p.add(b.r[34] == 4); assert p.check() == sat
    for i, code in enumerate((0xDC, 0xDE, 0xD4, 0xDD, 0xD4)):
        before = b; b, out = step(b, p, code, label+f'_header4_{i}')
        if code == 0xD4:
            indices = [j+3 for j in raw] if i == 2 else list(raw)
            w['prove'](p, And(eq([out[j] for j in indices], old_raw),
                *[out[j] == before.m[j] for j in range(42) if j % 3 != 0 or j >= 36]),
                label+' actual D4 copies six opaque old-M2 tetras; other lanes held, FULL numericM1 is overwritten')
        else: w['prove'](p, eq(out, before.m), label+' no extra header4 ring write', False)
    w['prove'](p, And(w['ip'](b) == 0xE5, b.s1 == 4, b.r[33] == old_raw[0]),
        label+' return E5 is NOT finished: A11 becomes RAW0')
    for i, code in enumerate((0xE5, 0xE6, 0xE4, 0xDE)):
        if code == 0xE5: p.add(b.m[22] == 15)
        before = b; b, out = step(b, p, code, label+f'_post{i}')
        w['prove'](p, eq(out, before.m), label+' real post-write dispatch has no ring write', False)
    w['prove'](p, And(w['ip'](b) == BitVecVal(0xD0, 8)+q['ZeroExt'](4, old_raw[0]),
        b.s1 == old_raw[0]), label+' real continuation is D0+RAW0, data-dependent')
    for value, code, end in ((3, 0xD3, 0x63), (13, 0xDD, 0xDD)):
        p.push(); p.add(old_raw[0] == value); assert p.check() == sat
        z, out = step(b, p, code, label+f'_restricted{value}')
        w['prove'](p, And(w['ip'](z) == end, eq(out, b.m)),
            label+f' RAW0={value:X}: true {end:02X} next point, no extra write')
        p.pop()
    print('PASS CONDITIONAL '+label+': source E4 word ->14 M2; earlier EE RAW6 '
          '->two numericM1 writes, ORIGINAL return used. RAW0three reaches63; '
          'RAW0D loops. Raw cache origin/slot matching/backup/safe ALL5 exit '
          'are not asserted. No native key witness.', flush=True)


def permanent_dd_loop():
    a = q['State']('a3cc_DD_self'); p = w['base'](a, 0xDD); p.add(a.s1 == 13)
    out = []; b = w['ex'](a, 0xDD, *q['arbitrary_keys']('a3cc_DD_self_keys'),
        serial_inputs=q['State']('a3cc_DD_self_serial').m, emitted_outputs=out)
    w['prove'](p, And(w['ip'](b) == 0xDD, b.s1 == 13, eq(out, a.m)),
        'GLOBAL original DD/S1D self-loop for ALL future key/serial signals; not a safe general exit')


def global_type2_no_inverse():
    a = q['State']('a3cc_global_type2'); p = w['base'](a, 0xA3)
    p.add(vector(a), a.r[26] == 0, a.r[32] == 2, a.r[35] == 13, a.s1 == 9,
        a.r[34] == 6, a.r[30] == 2, a.r[33] == 13,
        *[w['stack'](a)[j] == v for j, v in enumerate((0xDD, 0xE5, 0xAD))])
    b = a
    for i, code in enumerate((0xA3, 0xCC, 0xBB, 0xBC, 0xDD, 0xDA)):
        b, _ = step(b, p, code, f'a3cc_global_type2_{i}')
    w['prove'](p, And(w['ip'](b) == 0xDC, b.r[34] == 3),
        'GLOBAL native-packet TYPE2/A2: DA header4 impossible for ANY input B9/cache/marker wait')
    print('PASS TYPE2 exclusion is universal under the COMPLETE source packet, '
          'not the selected nine-wait composition. TYPE3 permits header4, '
          'but has no intervening A2 timing window after the last EE.', flush=True)


def diagonal_cc_interface():
    def dependency():
        counts, pairs = diagonal['selected_a3_source_cut']()
        diagonal['selected_data_provenance'](counts, pairs)
    checked('SAME diagonal A3 complete14/21 B8zero/TYPE2or3 source', dependency)
    a = q['State']('a3cc_diagonal'); p = w['base'](a, 0xA3)
    p.add(vector(a), basis['correlation'](a), a.r[25] == 0, a.r[26] == 0,
        a.s1 == 9, Or(a.r[32] == 2, a.r[32] == 3),
        *[w['stack'](a)[j] == v for j, v in enumerate((0x93, 0xE5, 0xAD))])
    b = a
    for i, code in enumerate((0xA3, 0xCC, 0xBB, 0xBC)):
        b, out = step(b, p, code, f'a3cc_diagonal_{i}')
    w['prove'](p, And(w['ip'](b) == 0x93, w['byte'](b.r[31], b.r[34]) == 0x3C,
        eq(out[1:42:3], [*B(a), q['N4'](3), q['N4'](10)])),
        'SAME diagonal/vectorCC ->CC/BB/BC gives fixed3C/true93, not3B or generic constantCC36')


def ring_geometry():
    # Read/verified immutable mk61.cjs: three IK memories42, two IR252;
    # tick() runs IK1302->1303->1306->IR2a->IR2b->closeRing. Tags here
    # model unmodified circulation only, not ROM or other-chip writes.
    lengths = (42, 42, 42, 252, 252); assert sum(lengths) == 630
    def at_word(n):
        memories = []; offset = 0
        for size in lengths:
            memories.append(list(range(offset, offset+size))); offset += size
        indices = [0]*5; origin = memories[0][1:36:3]
        for _ in range(n*42):
            carried = memories[0][indices[0]]
            for chip in range(1, 5):
                previous = memories[chip][indices[chip]]
                memories[chip][indices[chip]] = carried; carried = previous
            memories[0][indices[0]] = carried
            indices = [(index+1) % size for index, size in zip(indices, lengths)]
        return origin, memories[0][1:36:3]
    assert all((at_word(n)[0] == at_word(n)[1]) == (n % 15 == 0) for n in range(46))
    # EE, twoAD, optional w A2 words, A3,CC,BB,BC. A3 writes three
    # frames BEFORE BC, hence damages a different circulating carrier.
    assert 6 % 15 != 0
    compatible = [w for w in range(1, 31) if at_word(6+w)[0] == at_word(6+w)[1]]
    assert compatible == [9, 24]
    assert at_word(12)[1] != at_word(15)[1]
    print('PASS geometry-only CARRIER matching: TYPE3/noA2 EE->BC delta6 mismatches; '
          'TYPE2 with w A2 words needs w=9 mod15. Preliminary A3 upper3 '
          'targets another carrier (delta3 before BC), but TYPE2 forces header3. '
          'ROM data moves on other chips are not modelled by the tags. This is '
          'NOT native marker availability, physical Ms/programme identity or safe exchange.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    complete_constant_sources()
    read_and_wait_contracts()
    restored_header_contract()
    composed_dd_writer(3, 0)
    composed_dd_writer(2, 9)
    global_type2_no_inverse()
    permanent_dd_loop()
    diagonal_cc_interface()
    ring_geometry()
    r['inlet']['immutable_reference']()
    print('PASS constantCC earlier-read/DD-DA source audit. No native/live/ALL5 '
          'experiment, calculator-state/IP/return/ROM repair or full/partialK2 claim.', flush=True)
