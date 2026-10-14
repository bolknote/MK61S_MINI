#!/usr/bin/env python3
"""Original68/65 decoder inlet: a reset theorem, not a keyboard recipe.

The COMPLETE206-class source cut has only6D/60 external entries. The low
07 branch starts with type/number0; the high77 branch has an even type,
number=type+1, and77 ITSELF sets modeF/saved0/flag0. Consequently every
native68/65 inlet uses type6/8/A/C, number7/9/B/D, S1zero and modeF.
The subsequent original65/7B/B7/45/8B/48 cannot select DIRECT BC-C.
The B/BB branch is not excluded, nor are other48 sources or partialK2.
All pins/serial words are arbitrary; reference ROM/emulator are immutable.
"""
from collections import Counter, defaultdict, deque
from pathlib import Path
import runpy

from z3 import And, Extract, If, Implies, Or, UGE, ULE

root = Path(__file__).resolve().parent
parity = runpy.run_path(str(root / 'cache-bc-77-parity.py'))
source = parity['source']
r, w, q = (source[n] for n in ('r', 'w', 'q'))
states, edges = source['states'], source['edges']
walk = source['walk']
N8 = source['N8']
even = lambda a: Extract(0, 0, a.r[32]) == 0
low = lambda a: And(a.r[32] == 0, Or(a.r[29] == 0, a.r[29] == 1))
high = lambda a: And(even(a), a.r[29] == a.r[32]+1,
                     a.r[2] == 15, a.r[5] == 0, a.r[23] == 0)


def predecessor_counts(code):
    return Counter(states[i][0] for i, row in enumerate(edges)
                   for j in row if states[j][0] == code)


def source_cut():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    pred = defaultdict(set)
    for i, row in enumerate(edges):
        for j in row: pred[j].add(i)
    targets = {i for i, a in enumerate(states) if a[0] == 0x68
               and any(states[j][0] == 0x65 for j in edges[i])}
    assert len(targets) == 37
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] in (0x60, 0x6C): continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 206 and counts == {
        0x60: 19, 0x68: 37, 0x69: 37, 0xFB: 37,
        0xFD: 19, 0xFE: 19, 0xFC: 38}
    assert all(states[i][5] == [14] for i in region if states[i][0] != 0x60)
    external = Counter((states[i][0], states[j][0]) for i, row in enumerate(edges)
                       if i not in region for j in row if j in region)
    assert external == {(0x6D, 0x60): 23}
    internal = Counter((states[i][0], states[j][0])
                       for i in region for j in edges[i] if j in region)
    assert internal == {
        (0x60, 0x68): 19, (0x68, 0x69): 37, (0x69, 0xFB): 37,
        (0xFB, 0xFC): 37, (0xFB, 0xFD): 37, (0xFD, 0xFE): 19,
        (0xFE, 0xFC): 19, (0xFC, 0x68): 38}
    assert sum(internal.values()) == 243
    assert not region & set(graph['indexes']['roots'])
    assert predecessor_counts(0x60) == {0x6D: 227, 0x6C: 19}
    assert predecessor_counts(0x6D) == {7: 273, 0x77: 165}
    print('PASS COMPLETE68/65 source cut:206 classes/243 internal edges; '
          'only23 external6D→60 edges. NO C9/67/6C/F9 entry into this cut; '
          'the37 graph candidates are NOT native witnesses.', flush=True)
    return counts, internal


def exact_decoder_gates():
    for code in (0x65, 0x7B, 0xB7, 0x45, 0x8B, 0x68, 0x77):
        label = f'bc68_exact_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'), emitted_outputs=out)
        if code in (0x65, 0x7B, 0xB7, 0x45):
            next_code = {0x65: 0x7B, 0x7B: 0xB7, 0xB7: 0x45, 0x45: 0x8B}[code]
            claim = And(w['ip'](b) == next_code, b.r[29] == a.r[29]+a.s1,
                b.r[32] == a.r[32]+1, b.s1 == 0,
                *[b.r[j] == a.r[j] for j in (2, 5, 23, 26, 35, 38)])
        elif code == 0x8B:
            claim = And(w['ip'](b) == 0x48,
                b.r[29] == a.r[29]-a.r[2]-1, b.s1 == b.r[29],
                b.r[2] == a.r[5], *[b.r[j] == a.r[2] for j in (5, 8, 11, 14, 17, 20)],
                *[b.r[j] == a.r[j] for j in (23, 26, 32, 35, 38)])
        elif code == 0x68:
            claim = And(w['ip'](b) == If(And(UGE(a.r[29], 7), ULE(a.r[29], 14)),
                (q['ZeroExt'](4, a.r[38]^8) << 4) | N8(5), N8(0x69)),
                ((w['ip'](b) == 0x65) == And(a.r[38] == 14,
                    UGE(a.r[29], 7), ULE(a.r[29], 14))),
                *[b.r[j] == a.r[j] for j in (2, 5, 23, 26, 29, 32, 35, 38)],
                b.s1 == a.s1)
        else:
            claim = And(b.r[2] == 15, b.r[5] == 0, b.r[23] == 0, b.s1 == 0,
                *[b.r[j] == a.r[j] for j in (26, 29, 32, 35, 38)])
        # The numeric12 are held, NOT the full14 B tetras or stack services.
        w['prove'](p, And(claim,
            w['eq'](b.r[0:36:3], a.r[0:36:3]),
            w['eq'](b.r[1:36:3], a.r[1:36:3]),
            w['eq'](b.st[:36], a.st[:36]), w['eq'](out, a.m)),
            f'original{code:02X} exact controls; numericA12/B12/ST held, no ring write')


def low07_number_cut():
    """The old low-type proof is strengthened by the actual ZERO operand."""
    expected = {0xC9: {0xCD: 492},
        6: {0x55: 209, 0x38: 48, 0x3A: 178, 0xC9: 85}, 7: {6: 273}}
    for code, parents in expected.items(): assert predecessor_counts(code) == parents

    def invariant(a, code):
        if code == 0xC9: return a.r[38] == 8
        if code in (6, 7): return Or(a.r[38] == 8, And(a.r[32] == 0, a.r[29] == 0))
        return And()

    for code in (0xCD, 0xC9, 0x55, 0x38, 0x3A, 6):
        label = f'bc68_low07_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        targets = [target for target, parents in expected.items() if code in parents]
        w['prove'](p, And(*[Implies(w['ip'](b) == target, invariant(b, target))
            for target in targets]), f'ALL original{code:02X} preserves low07 ZERO-number cut')
    a = q['State']('bc68_low07_to6D'); p = w['base'](a, 7); p.add(invariant(a, 7))
    b = w['ex'](a, 7, *q['arbitrary_keys']('bc68_low07_to6D_keys'))
    w['prove'](p, Implies(And(w['ip'](b) == 0x6D, b.r[38] == 14),
        And(b.r[32] == 0, b.r[29] == 0)),
        'ALL reset07/selectorE→6D have BOTH type0 and number0, not arbitrary numberD')


def high77_e_number_cut():
    """Apply the previous all25/kind7 induction to the OTHER selectorE."""
    parity['all_nonzero_kind7_cut']()
    pred = defaultdict(set)
    for i, row in enumerate(edges):
        for j in row: pred[j].add(i)
    targets = {i for i, a in enumerate(states) if a[0] == 0x77
        and (a[5] is None or 14 in a[5])
        and (a[7] is None or any(n != 0 for n in a[7]))}
    assert len(targets) == 24
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] == 0x25: continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 388 and counts == {
        1: 30, 2: 30, 3: 30, 4: 30, 0x25: 58, 0x26: 24, 0x28: 24,
        0x77: 24, 0x7E: 24, 0xBA: 30, 0xCB: 30, 0xD4: 24, 0xDD: 30}
    assert all(states[i][3] == [4] for i in region if states[i][0] in (1, 2, 3, 4))
    external = Counter((states[i][0], states[j][0]) for i, row in enumerate(edges)
                       if i not in region for j in row if j in region)
    assert external == {(0x24, 0x25): 25, (0x23, 0x25): 22,
                        (0x36, 0x25): 8, (0x1D, 0x25): 4}
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
    internal = Counter((states[i][0], states[j][0])
                       for i in region for j in edges[i] if j in region)
    expected = {1: {1, 2}, 2: {2, 3}, 3: {4}, 4: {0xBA}, 0x25: {1},
        0x26: {0x28}, 0x28: {0x7E}, 0x77: set(), 0x7E: {0x7E, 0x77},
        0xBA: {0xCB}, 0xCB: {0xDD}, 0xD4: {0x26}, 0xDD: {0xD4}}
    assert {code: {dst for first, dst in internal if first == code}
            for code in counts} == expected

    def invariant(a, code):
        if code in (0x25, 1): return Implies(a.r[35] == 7, even(a))
        if code == 2: return Implies(a.r[35] == 7, And(even(a), ULE(a.r[29], a.r[32])))
        claim = And(even(a), a.r[29] == a.r[32]+1)
        return claim if code == 0x77 else Implies(a.r[35] == 7, claim)

    for code in sorted(counts):
        if not expected[code]: continue
        label = f'bc68_last25_E_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        if code in (1, 2, 3, 4): p.add(a.s1 == 4)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, invariant(b, dst))
            for dst in sorted(expected[code])]),
            f'ALL original{code:02X} preserves selectorE last25 exact-number invariant')
    print('PASS GLOBAL selectorE77: even type, EXACT number=type+1. '
          'The388-class last25 cut and unbounded01/02 induction leave no free counter.', flush=True)


def joint68_induction():
    counts, internal = source_cut()
    # At60 the other6C source has selector8. The original6D holds all
    # control fields and enters60 only with nonzeroR26. Its two parents
    # are07 (type/number0 at selectorE) and77 (even number=type+1,
    # with its own mandatory modeF/saved0/flag0 writes).
    inlet = lambda a: Or(a.r[38] != 14, a.r[26] == 0,
        And(a.r[32] == 0, a.r[29] == 0), high(a))
    a = q['State']('bc68_high77_to6D'); p = w['base'](a, 0x77)
    p.add(a.r[38] == 14, a.r[26] != 0, even(a), a.r[29] == a.r[32]+1)
    b = w['ex'](a, 0x77, *q['arbitrary_keys']('bc68_high77_to6D_keys'))
    w['prove'](p, And(high(b), inlet(b)),
        'ALL reset-shaped selectorE77 establish joint6D inlet, any OLD mode/pins')
    for code in (0x6C, 0x6D):
        label = f'bc68_upstream_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inlet(a))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, Implies(w['ip'](b) == 0x60, inlet(b)),
            f'ALL original{code:02X} establishes/preserves joint60 inlet')
        if code == 0x6D:
            w['prove'](p, Implies(w['ip'](b) == 0x60, b.r[26] != 0),
                'original6D→60 excludes the zero-R26 alternative')

    def invariant(a, code):
        if code == 0x60: return And(inlet(a), a.r[26] != 0)
        common = And(a.r[38] == 14, a.r[26] != 0)
        if code in (0x68, 0x69): return And(common, Or(low(a), And(high(a), a.s1 == 0)))
        return And(common, a.r[32] == 0, a.r[29] == 1)

    for code in sorted(counts):
        label = f'bc68_joint_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        targets = sorted({dst for first, dst in internal if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, invariant(b, dst))
            for dst in targets]), f'ALL original{code:02X} preserves COMPLETE206 joint invariant')
        if code == 0x68:
            w['prove'](p, Implies(w['ip'](b) == 0x65,
                And(high(b), b.s1 == 0,
                    Or(*[b.r[32] == k for k in (6, 8, 10, 12)]))),
                'ALL native68→65: type6/8/A/C, number7/9/B/D, modeF/saved0/flag0/S1zero')
    print('PASS low07 branch: number0→FB/FC/number1→69/6A outside the E cut; '
          'never65. High77 number=type+1 can NEVER take69→FB. Thus no FC-produced '
          '65 inlet is native, irrespective of programme data or future keys.', flush=True)


def original68_decoder_exits():
    exits = {
        6: ((0xB1,), 0xB2),
        8: ((0xB1, 0xB3), 0xB9),
        10: ((0xB1, 0xB3), 0xBB),
        12: ((0x4A, 0x4C), 0x4E),
    }
    for typ, (suffix, expected) in exits.items():
        label = f'bc68_native_shape_type{typ:X}'
        a = q['State'](label); p = w['base'](a, 0x68)
        p.add(a.r[38] == 14, a.r[26] != 0, a.r[32] == typ,
              a.r[29] == typ+1, a.r[2] == 15, a.r[5] == 0, a.r[23] == 0, a.s1 == 0)
        b = walk(a, p, (0x68, 0x65, 0x7B, 0xB7, 0x45, 0x8B), label+'_prefix')
        w['prove'](p, And(w['ip'](b) == 0x48, b.r[32] == (typ+4) % 16,
            b.r[29] == typ+1, b.r[2] == 0, b.r[5] == 15, b.r[23] == 0,
            w['eq'](b.r[0:36:3], a.r[0:36:3]),
            w['eq'](b.r[1:36:3], a.r[1:36:3]), w['eq'](b.st[:36], a.st[:36])),
            f'reset-shaped68/type{typ:X}: type+4, ODD operand, ALL numeric buffers held')
        b = walk(b, p, (0x48, *suffix), label+'_exit')
        w['prove'](p, w['ip'](b) == expected,
            f'original68/type{typ:X} exact next frontier{expected:02X}, NOT direct BC-C')
    print('PASS GLOBAL DIRECT68/65/8B→BC-C CLOSED: exact frontiers B2/B9/BB/4E. '
          'BB is still a possible limited16-byte route, NOT an arbitrary-byte '
          'writer or a native exchange witness. Other48 entries/later routes remain open.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    exact_decoder_gates()
    low07_number_cut()
    high77_e_number_cut()
    joint68_induction()
    original68_decoder_exits()
    r['inlet']['immutable_reference']()
    print('PASS original68 source/control audit. No emulator/ROM changes, no '
          'new keyboard sequence, no general partialK2 impossibility claim.', flush=True)
