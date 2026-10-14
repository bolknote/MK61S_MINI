#!/usr/bin/env python3
"""Original28 source provenance and a CONDITIONAL zero-counter preparer.

The complete reset graph supplies caller coverage, not native witnesses.
The nonzero07 origin theorem is conditional at the seven selected6E
boundaries. The three-pass preparer assumes a joint zero07 control packet;
it does NOT establish that packet through public keys, physical Ms origin,
ring phase, ordinary-register safety, an inverse or partialK2 exchange.
All positive paths execute ORIGINAL ROM and construct their own returns.
"""
from collections import Counter, defaultdict, deque
from pathlib import Path
import runpy

from z3 import And, Extract, Implies, Or, UGE, ULE, sat, unsat

root = Path(__file__).resolve().parent
inlet = runpy.run_path(str(root / 'cache-bc-28-inlet.py'))
r, w, q, states, edges, walk = (inlet[n] for n in
    ('r', 'w', 'q', 'states', 'edges', 'walk'))
even = lambda a: Extract(0, 0, a.r[32]) == 0
wanted = lambda a: Or(a.r[35] == 9, a.r[35] == 11)
shape = lambda a: a.r[38] == a.r[35]+8
low_flag = lambda a: ULE(a.r[23], 2)
origin = lambda a: Implies(wanted(a), Or(low_flag(a), shape(a)))
ALLOWED_BYTES = [0, *range(0xC3, 0xCA),
                 *[16*high+low for high in (13, 14, 15) for low in range(10)]]
assert len(ALLOWED_BYTES) == 38


def predecessors():
    pred = defaultdict(set)
    for i, row in enumerate(edges):
        for j in row: pred[j].add(i)
    return pred


def source_cut():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    pred = predecessors()
    targets = {i for i, a in enumerate(states) if a[0] == 7
        and (a[5] is None or set(a[5]) & {9, 10})
        and (a[7] is None or any(v != 0 for v in a[7]))}
    assert len(targets) == 26
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] in (0x1F, 0x1C, 0x6E): continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 1345 and counts == {
        1: 41, 2: 41, 3: 41, 4: 41, 6: 26, 7: 26,
        0x18: 67, 0x1A: 22, 0x1B: 67, 0x1C: 88, 0x1D: 67, 0x1F: 22,
        0x20: 19, 0x21: 19, 0x22: 12, 0x23: 22, 0x24: 25, 0x25: 58,
        0x26: 26, 0x27: 2, 0x28: 49, 0x2C: 25, 0x2D: 22,
        0x2E: 28, 0x2F: 29, 0x36: 12, 0x38: 1, 0x3A: 49,
        0x60: 43, 0x61: 50, 0x6D: 47, 0x6E: 7, 0x77: 47, 0x7E: 47,
        0xBA: 41, 0xCB: 41, 0xD4: 24, 0xD6: 10, 0xDD: 41}
    assert not region & set(graph['indexes']['roots'])
    internal = Counter((states[i][0], states[j][0])
        for i in region for j in edges[i] if j in region)
    assert sum(internal.values()) == 1702
    external = Counter((states[i][0], states[j][0])
        for i, row in enumerate(edges) if i not in region for j in row if j in region)
    assert external == {(0x19, 0x1C): 44, (0x1E, 0x1C): 22,
                        (0xA5, 0x1F): 30, (0x62, 0x6E): 7}
    assert all(states[i][7] == [15] for i in region if states[i][0] in (0x1F, 0x1A))
    # Neither55 nor a C9 return supplies pointer9/A AND a nonzero counter.
    assert 0x55 not in counts and 0xC9 not in counts
    print('PASS COMPLETE nonzero07/selector9/A origin cut:26 targets; '
          '1345 classes/1702 internal edges/39 ROM words; only1F/1C/6E '
          'boundaries, no root. Graph paths are NOT native witnesses.', flush=True)
    return region, counts, internal


def all_1c_selector_provenance():
    pred = predecessors()
    expected = {0x1C: {0x1F: 48, 0x19: 96, 0x1E: 48},
                0x19: {0x1F: 48, 0x17: 48},
                0x17: {0x1F: 48}, 0x1E: {0x1F: 48}}
    for code, parents in expected.items():
        assert Counter(states[j][0] for i, a in enumerate(states)
                       if a[0] == code for j in pred[i]) == parents
    for code in (0x1F, 0x17, 0x19, 0x1E):
        label = f'bc28_origin_1c_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        if code != 0x1F: p.add(shape(a))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, shape(b),
            f'ALL original{code:02X} establishes/preserves selector=kind+8')
    print('PASS GLOBAL1C selector=kind+8: ALL four parent families covered; '
          'kinds9/B carry selector1/3, not free9/A.', flush=True)


def origin_invariant(a, code):
    typ = a.r[32]; f = a.r[26] == 15
    if code == 0x1F: return And()
    if code == 0x1C: return shape(a)
    if code in (0x6E, 0x61, 0x3A, 0x27, 0x38): return origin(a)
    if code in (6, 7):
        return And(origin(a), Or(And(typ == 0, a.r[29] == 0), a.r[38] == 8))
    if code in (0x6D, 0x60):
        return And(origin(a), Or(even(a), a.r[38] == 8))
    if code == 0x77: return And(even(a), a.r[35] == 7)
    if code == 0x1A: return And(typ == 0, shape(a))
    if code in (0x18, 0x1B, 0x1D):
        parity = (Or(Extract(0, 0, typ) == 1, And(f, Or(typ == 0, typ == 2)))
                  if code == 0x1B else Or(even(a), And(f,
                      typ == 1 if code == 0x18 else Or(typ == 1, typ == 3))))
        return And(parity, Implies(wanted(a), Or(low_flag(a), And(f, shape(a)))))
    if code == 0x2D: return And(typ == 2, shape(a))
    if code == 0x2C: return And(Or(even(a), typ == 1, typ == 3), origin(a))
    return And(Implies(a.r[35] == 7, even(a)), Implies(wanted(a), low_flag(a)))


def conditional_origin_induction():
    region, counts, internal = source_cut()
    all_1c_selector_provenance()
    for code in sorted(counts):
        label = f'bc28_origin_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(origin_invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        targets = sorted({dst for first, dst in internal if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, origin_invariant(b, dst))
                           for dst in targets]),
            f'ALL original{code:02X} preserves CONDITIONAL39-word source invariant')
        # No resolver loop can raise a low control flag to >=3.
        w['prove'](w['base'](a, code), b.r[23] == (0 if code == 0x77 else a.r[23]),
            f'original{code:02X} exact flag transfer (77 clears, all others hold)', False)
    print('PASS CONDITIONAL source theorem: if selected6E boundaries satisfy '
          'wanted-kind⇒(flag0..2 OR selector=kind+8), every target07 does too. '
          'Thus the required nonzero07 joint packet must import its high '
          'flag/mismatched selector through selected6E, not create it in '
          '1F/1C or resolver loops. This is NOT a global impossibility proof.', flush=True)
    return region


def zero07_frontier():
    """Complete graph coverage of the NEW inlet, not a positive proof."""
    pred = predecessors()
    targets = {i for i, a in enumerate(states) if a[0] == 7
        and (a[5] is None or set(a[5]) & {9, 10})
        and (a[7] is None or 0 in a[7])}
    assert len(targets) == 11
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] in (0x1F, 0x1C, 0x6E, 0xA3): continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 620 and len(counts) == 31 and counts == {
        1: 8, 2: 8, 3: 8, 4: 8, 6: 11, 7: 11, 0x12: 48,
        0x18: 52, 0x1A: 26, 0x1B: 52, 0x1C: 104, 0x1D: 52, 0x1F: 48,
        0x20: 8, 0x21: 8, 0x22: 9, 0x27: 26, 0x2E: 26, 0x2F: 16,
        0x36: 9, 0x37: 8, 0x38: 19, 0x3A: 7, 0x55: 1, 0x61: 7,
        0x6E: 7, 0xA3: 1, 0xBA: 8, 0xCB: 8, 0xD6: 8, 0xDD: 8}
    internal = Counter((states[i][0], states[j][0])
        for i in region for j in edges[i] if j in region)
    assert sum(internal.values()) == 772
    external = Counter((states[i][0], states[j][0])
        for i, row in enumerate(edges) if i not in region for j in row if j in region)
    assert external == {(0xA5, 0x1F): 56, (0x19, 0x1C): 52,
        (0x1E, 0x1C): 26, (0x62, 0x6E): 7, (0xAD, 0xA3): 2, (0xA2, 0xA3): 1}
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
    # A graph12 edge includes ORIGINAL C6. Never execute12 as if it
    # returned38 directly when proving the actual ROM path.
    assert r['inlet']['g']['graph']['metadata']['fusedCommands']['12'] == ['12', 'C6']
    print('PASS COMPLETE NEW zero07/selector9/A frontier:11 targets; '
          '620 classes/772 internal edges/31 graph words; only1F/1C/6E/A3 '
          'boundaries. The sole55 class comes from A3. This is graph '
          'coverage ONLY (12 includes C6), NOT a native constructor.', flush=True)


def selected_counter_source(region):
    pred = predecessors()
    current = {i for i in region if states[i][0] == 0x6E}
    assert len(current) == 7
    for previous, size, links in ((0x62, 7, 7), (0x6F, 7, 7), (0x6D, 8, 8)):
        parents = {j for i in current for j in pred[i]}
        assert len(parents) == size
        assert Counter(states[j][0] for i in current for j in pred[i]) == {previous: links}
        if previous == 0x6F: assert all(states[i][7] == [0] for i in parents)
        current = parents
    assert Counter(states[j][0] for i in current for j in pred[i]) == {0x77: 16, 7: 11}
    for code in (0x6D, 0x6F, 0x62, 0x6E, 0x61, 0x3A, 6):
        label = f'bc28_origin_counter_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        if code == 0x6D:
            claim = And((w['ip'](b) == 0x6F) == (a.r[26] == 0),
                        w['stack'](b)[0] == 0x6E)
        elif code in (0x6F, 0x62):
            claim = b.r[26] == a.r[1]+1
        else: claim = b.r[26] == a.r[26]
        held = (2, 5, 23, 29, 32, 35, 38) if code != 6 and code != 0x3A else (
                2, 5, 23, 35, 38)
        w['prove'](p, And(claim, *[b.r[j] == a.r[j] for j in held]),
            f'original{code:02X} actual counter/return/control transfer')
    print('PASS selected seven6E sources: ONLY62←6F←6D/R26zero; '
          '6D parents07/77, but77 clears the needed flag. Necessary earlier '
          'zero-counter07 packet remains UNPROVED through native keys. '
          'Per-word6F/62 uses OLD B0+1; B0 changes, so composition is NOT '
          'initialB0+1.', flush=True)


def zero_counter_preparer(kind, mode, pointer, address, label):
    """A conditional factory supplying the actual entry to the writer test.

    No symbolic state/return is repaired. All assumptions occur at OLD07.
    The byte domain is exact for this three-pass/3A route, NOT for every
    future continuation. Counter is OLD B1+1, because6F shifts B first.
    """
    a = q['State'](label+'_zero07'); p = w['base'](a, 7)
    p.add(a.r[32] == 0, a.r[29] == 0, a.r[26] == 0, a.r[2] == mode,
        a.r[35] == kind, a.r[38] == pointer, UGE(a.r[23], 3),
        a.r[4] == 10 if kind == 9 else a.r[4] != 15,
        Or(*[w['byte'](a.r[31], a.r[34]) == value for value in ALLOWED_BYTES]),
        a.st[1] == 5, a.st[22] == 1, a.st[25] == 0,
        a.st[30] == address % 10, a.st[33] == address // 10)
    b = walk(a, p, (7, 0x6D, 0x6F, 0x62, 0x6E), label+'_prepare_counter')
    for cycle in range(1, 4):
        b = walk(b, p, (0x61, 0x3A, 6), label+f'_prepare_increment{cycle}')
        if cycle < 3:
            b = walk(b, p, (7, 0x6D, 0x60), label+f'_prepare_retry{cycle}')
            w['prove'](p, w['ip'](b) == 0x61,
                'original60 first TWO preparation passes must return61', False)
    # The preparation does not preserve the original numericA12. Verify
    # the destructive shape explicitly instead of assuming A rotated twice.
    expected_a = [q['N4'](15), a.r[27], a.r[30], *([q['N4'](15)]*9)]
    expected_b = [*a.r[7:36:3], a.r[31], a.r[34]]
    assert len(expected_a) == len(expected_b) == 12
    w['prove'](p, And(w['ip'](b) == 7,
        *[b.r[j] == a.r[j] for j in (2, 5, 23, 29, 32, 35, 38)],
        b.r[26] == a.r[4]+1, b.r[26] == 11 if kind == 9 else b.r[26] != 0,
        b.r[25] == b.r[31], b.r[31] == a.r[31], b.r[34] == a.r[34],
        w['eq'](b.st[:36], a.st[:36]),
        w['eq'](b.r[0:36:3], expected_a), w['eq'](b.r[1:36:3], expected_b)),
        f'CONDITIONAL zero07 kind{kind:X}/address{address}: exact3 passes prepare '
        'ready nonzero07, inputbyte/ST held, A12 destructively replaced')
    p.push()
    assert q['possible_values'](w['byte'](b.r[31], b.r[34]), p, 257) == ALLOWED_BYTES
    p.pop()
    return b, p


def exact_three_pass_byte_domain():
    # Do not prefilter byte values in the converse: all OLD B10/B11 and
    # numericST are arbitrary. Numeric61→3A choices are explicit PRIMARY
    # hypotheses here; the factory above proves them from the allowed set.
    for kind, mode, pointer in ((9, 15, 9), (11, 7, 10)):
        label = f'bc28_origin_byte_converse_kind{kind:X}'
        a = q['State'](label); p = w['base'](a, 7)
        p.add(a.r[32] == 0, a.r[29] == 0, a.r[26] == 0, a.r[35] == kind,
              a.r[2] == mode, a.r[38] == pointer, UGE(a.r[23], 3),
              a.r[4] == 10 if kind == 9 else a.r[4] != 15)
        b = walk(a, p, (7, 0x6D, 0x6F, 0x62, 0x6E), label+'_counter')
        for cycle in range(1, 4):
            b = walk(b, p, (0x61,), label+f'_gate{cycle}')
            p.add(w['ip'](b) == 0x3A)
            assert p.check() == sat
            b = walk(b, p, (0x3A, 6), label+f'_increment{cycle}')
            p.push(); p.add(b.r[25] == b.r[31])
            if cycle < 3: assert p.check() == unsat
            else:
                assert p.check() == sat
                w['prove'](p, And(b.r[31] == a.r[31], b.r[34] == a.r[34]),
                    'exact THIRD preparation pass restores the initial byte')
                assert q['possible_values'](w['byte'](b.r[31], b.r[34]), p, 257) == ALLOWED_BYTES
            p.pop()
            if cycle < 3:
                b = walk(b, p, (7, 0x6D, 0x60), label+f'_retry{cycle}')
                w['prove'](p, w['ip'](b) == 0x61,
                    'exact first/TWO passes are not ready;60 forces61', False)
    print('PASS EXACT selected three-pass byte domain:00, C3..C9, D0..D9, '
          'E0..E9, F0..F9 (38/256 bytes). One/TWO passes never ready. '
          'A12 becomes[F,oldA9,oldA10,F×9], B12 becomes '
          '[oldB2..B11,oldB10,oldB11]; original full A12 is NOT retained.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    region = conditional_origin_induction()
    selected_counter_source(region)
    zero07_frontier()
    exact_three_pass_byte_domain()
    inlet['conditional_two_decoder_writers'](
        entry_factory=zero_counter_preparer, byte_values=ALLOWED_BYTES,
        label_prefix='bc28_zero07_two_decoder')
    r['inlet']['immutable_reference']()
    print('PASS origin/source/preparer/component audit. No native keyboard '
          'capture, hardware run, state/ROM/return repair, physical Ms '
          'exchange or general partialK2 impossibility claim.', flush=True)
