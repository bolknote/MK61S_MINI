#!/usr/bin/env python3
"""Global even-type cut for the ORIGINAL1D/R26eight→25 constructor.

The audited COMPLETE reset graph isolates a62-class feedback region with
only06→07 external edges. Every boundary07 has type0 OR selector8. The
18/1B pair adds2, while the25 marker/resolver cycle holds the type. A
node-sensitive bit invariant therefore excludes every odd type at the
R26eight1D entries, for unlimited key/marker/serial timing. A wider1070
class region covers every nonzero25 parent and proves kind7⇒even type.
The actual25 counter produces an odd operand; a388-class last25 cut
therefore excludes the direct high77/selectorC/operandC writer. This does
NOT exclude the other48/8B entry, every77 continuation or partialK2.
"""
from collections import Counter, defaultdict, deque
from pathlib import Path
import runpy

from z3 import And, Extract, If, Implies, Or, ULE

root = Path(__file__).resolve().parent
source = runpy.run_path(str(root / 'cache-bc-77-producer.py'))
r, w, q = (source[n] for n in ('r', 'w', 'q'))
states, edges = source['states'], source['edges']


def closed_feedback_region():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])
    pred = defaultdict(set)
    for i, row in enumerate(edges):
        for j in row: pred[j].add(i)
    targets = {i for i, a in enumerate(states) if a[0] == 0x1D and
        (a[7] is None or 8 in a[7])}
    assert len(targets) == 4
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] in (0x25, 7): continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 62 and counts == {
        1: 3, 2: 3, 3: 3, 4: 3, 7: 6, 0x18: 4, 0x1B: 4, 0x1D: 4,
        0x25: 3, 0x26: 2, 0x28: 2, 0x60: 4, 0x6D: 6, 0x77: 2,
        0x7E: 2, 0xBA: 3, 0xCB: 3, 0xD4: 2, 0xDD: 3}
    external = Counter((states[i][0], states[j][0]) for i, row in enumerate(edges)
        if i not in region for j in row if j in region)
    assert external == {(6, 7): 6}
    assert not region & set(graph['indexes']['roots'])
    internal = Counter((states[i][0], states[j][0]) for i in region for j in edges[i] if j in region)
    assert internal == {
        (7, 0x6D): 6, (0x6D, 0x60): 6, (0x60, 0x18): 4,
        (0x18, 0x1B): 4, (0x1B, 0x1D): 4, (0x1D, 0x25): 4,
        (0x25, 1): 3, (1, 1): 3, (1, 2): 3, (2, 2): 3, (2, 3): 3,
        (3, 4): 3, (4, 0xBA): 3, (0xBA, 0xCB): 3, (0xCB, 0xDD): 3,
        (0xDD, 0xD4): 3, (0xD4, 0x26): 2, (0x26, 0x28): 2,
        (0x28, 0x7E): 2, (0x7E, 0x7E): 2, (0x7E, 0x77): 2, (0x77, 0x6D): 2}
    assert sum(internal.values()) == 70
    print('PASS COMPLETE62-class feedback cut:70 internal edges, onlysix external06→07 '
          'edges; all four1D/R26eight classes included. No free-state reachability claim.', flush=True)
    return counts, internal


def even_type_induction():
    counts, internal = closed_feedback_region()
    source['prior']['low_type_reset_cut']()
    even = lambda a: Extract(0, 0, a.r[32]) == 0

    def invariant(a, code):
        if code == 7: return Or(a.r[32] == 0, a.r[38] == 8)
        if code in (0x6D, 0x60): return Or(even(a), a.r[38] == 8)
        if code == 0x1B: return Extract(0, 0, a.r[32]) == 1
        return even(a)

    for code in sorted(counts):
        label = f'bc77_parity_word{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        targets = sorted({target for first, target in internal if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == target, invariant(b, target))
            for target in targets]), f'ALL original{code:02X} preserves feedback bit invariant')
    print('PASS GLOBAL RESET1D/R26eight: type ALWAYS EVEN (0/2/4/6/8/A/C/E), '
          'neverB/any odd type. The original1D→25/typeB high77/C writer constructor '
          'is impossible natively, including arbitrarily many resolver loops. '
          'Other25 parents/non-eight counters/other writer routes are NOT excluded.', flush=True)


def all_nonzero_kind7_cut():
    """Follow OTHER25 parents too; a conditional odd type must lose kind7."""
    pred = defaultdict(set)
    for i, row in enumerate(edges):
        for j in row: pred[j].add(i)
    targets = {i for i, a in enumerate(states) if a[0] == 0x25 and
        (a[7] is None or any(n != 0 for n in a[7]))}
    assert len(targets) == 58
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] in (7, 0x1F, 0x1C): continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 1070 and counts == {
        1: 41, 2: 41, 3: 41, 4: 41, 7: 15, 0x18: 63, 0x1A: 22,
        0x1B: 63, 0x1C: 88, 0x1D: 63, 0x1F: 22, 0x20: 19, 0x21: 19,
        0x22: 10, 0x23: 22, 0x24: 25, 0x25: 58, 0x26: 24, 0x28: 26,
        0x2C: 25, 0x2D: 22, 0x2E: 28, 0x2F: 29, 0x36: 10, 0x60: 21,
        0x6D: 25, 0x77: 25, 0x7E: 25, 0xBA: 41, 0xCB: 41,
        0xD4: 24, 0xD6: 10, 0xDD: 41}
    external = Counter((states[i][0], states[j][0]) for i, row in enumerate(edges)
        if i not in region for j in row if j in region)
    assert external == {(0x19, 0x1C): 44, (0x1E, 0x1C): 22, (0xA5, 0x1F): 30, (6, 7): 15}
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
    internal = Counter((states[i][0], states[j][0]) for i in region for j in edges[i] if j in region)
    assert sum(internal.values()) == 1340
    expected = {
        1: {1, 2}, 2: {2, 3}, 3: {4}, 4: {0xBA}, 7: {0x6D},
        0x18: {0x1B}, 0x1A: {0x18}, 0x1B: {0x1D}, 0x1C: {0x2D},
        0x1D: {0x20, 0x21, 0x23, 0x24, 0x25, 0x2C, 0x2E, 0x2F},
        0x1F: {0x18, 0x1A, 0x1B, 0x1C, 0x1D}, 0x20: {0x2F},
        0x21: {0x22, 0x23}, 0x22: {0x36}, 0x23: {0x24, 0x25},
        0x24: {0x25}, 0x25: {1}, 0x26: {0x28}, 0x28: {0x7E},
        0x2C: {0x2E}, 0x2D: {0x2C}, 0x2E: {1}, 0x2F: {0x20, 0x21},
        0x36: {0x25, 0x28}, 0x60: {0x18}, 0x6D: {0x60}, 0x77: {0x6D},
        0x7E: {0x77, 0x7E}, 0xBA: {0xCB}, 0xCB: {0xDD}, 0xD4: {0x26},
        0xD6: {0x2F}, 0xDD: {0xD4, 0xD6}}
    assert {code: {dst for first, dst in internal if first == code} for code in counts} == expected
    assert all(states[i][7] == [15] for i in region if states[i][0] in (0x1F, 0x1A))
    even = lambda a: Extract(0, 0, a.r[32]) == 0

    for code in (0x1F, 0x1C, 0x2C):
        label = f'bc77_kind7_generator{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        claim = (b.r[32] == 0 if code == 0x1F else b.r[32] == 2 if code == 0x1C else
            And(b.r[32] == a.r[35], b.r[35] == a.r[32]))
        w['prove'](p, claim, f'original{code:02X} exact unconditional type/kind generator')

    def invariant(a, code):
        if code in (0x1F, 0x1C): return And()
        if code == 7: return Or(a.r[32] == 0, a.r[38] == 8)
        if code in (0x6D, 0x60): return Or(even(a), a.r[38] == 8)
        if code == 0x77: return even(a)
        if code == 0x1A: return a.r[32] == 0
        if code == 0x18: return Or(even(a), And(a.r[26] == 15, a.r[32] == 1))
        if code == 0x1B: return Or(Extract(0, 0, a.r[32]) == 1,
            And(a.r[26] == 15, Or(a.r[32] == 0, a.r[32] == 2)))
        if code == 0x1D: return Or(even(a),
            And(a.r[26] == 15, Or(a.r[32] == 1, a.r[32] == 3)))
        if code == 0x2D: return a.r[32] == 2
        if code == 0x2C: return Or(even(a), a.r[32] == 1, a.r[32] == 3)
        return Implies(a.r[35] == 7, even(a))

    for code in sorted(counts):
        label = f'bc77_all_kind7_word{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, invariant(b, dst))
            for dst in sorted(expected[code])]), f'ALL original{code:02X} preserves kind7/type correlation')
    print('PASS COMPLETE1070/1340 kind7 cut: ALL nonzeroR26 original25 entries '
          'withkind7 have EVEN type. Other23/24/36 parents do NOT provide '
          'typeB/kind7.1F resets0;1C resets2;2C swaps an even or1/3 old type into kind, '
          'preventing an imported odd high type from retaining kind7. '
          'This is a global source induction, not bounded keyboard timing.', flush=True)


def high77_operand_cut():
    """The last real25 call makes an odd number, neverC, at high77."""
    pred = defaultdict(set)
    for i, row in enumerate(edges):
        for j in row: pred[j].add(i)
    targets = {i for i, a in enumerate(states) if a[0] == 0x77 and
        (a[5] is None or 12 in a[5]) and (a[7] is None or any(n != 0 for n in a[7]))}
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
    internal = Counter((states[i][0], states[j][0]) for i in region for j in edges[i] if j in region)
    expected = {1: {1, 2}, 2: {2, 3}, 3: {4}, 4: {0xBA}, 0x25: {1},
        0x26: {0x28}, 0x28: {0x7E}, 0x77: set(), 0x7E: {0x7E, 0x77},
        0xBA: {0xCB}, 0xCB: {0xDD}, 0xD4: {0x26}, 0xDD: {0xD4}}
    assert {code: {dst for first, dst in internal if first == code} for code in counts} == expected
    even = lambda a: Extract(0, 0, a.r[32]) == 0
    odd_number = lambda a: Extract(0, 0, a.r[29]) == 1

    # An actual01 loop initializes0 on EVERY iteration. Actual02 has a
    # monotonically increasing counter below the fixed even type; on exit
    # the number is exactly type+1, independent of marker wait duration.
    a = q['State']('bc77_counter01'); p = w['base'](a, 1); p.add(a.s1 == 4)
    b = w['ex'](a, 1, *q['arbitrary_keys']('bc77_counter01_keys'))
    w['prove'](p, And(w['ip'](b) == If(a.m[22] == 15, q['BitVecVal'](2, 8), q['BitVecVal'](1, 8)),
        b.r[29] == 0, b.r[32] == a.r[32], b.r[35] == a.r[35], b.s1 == 4),
        'original25 wait01 initializes0, holds type/kind/S1; unlimited marker wait')
    a = q['State']('bc77_counter02'); p = w['base'](a, 2)
    p.add(a.s1 == 4, even(a), ULE(a.r[29], a.r[32]))
    b = w['ex'](a, 2, *q['arbitrary_keys']('bc77_counter02_keys'))
    w['prove'](p, And(Or(w['ip'](b) == 2, w['ip'](b) == 3),
        b.r[29] == a.r[29]+1, b.r[32] == a.r[32], b.r[35] == a.r[35], b.s1 == 4,
        Implies(w['ip'](b) == 2, ULE(b.r[29], b.r[32])),
        Implies(w['ip'](b) == 3, And(b.r[29] == a.r[32]+1, odd_number(b)))),
        'original02 exact even-type counter induction/odd operand at exit03')

    def invariant(a, code):
        if code in (0x25, 1): return Implies(a.r[35] == 7, even(a))
        if code == 2: return Implies(a.r[35] == 7, And(even(a), ULE(a.r[29], a.r[32])))
        if code == 0x77: return And(even(a), odd_number(a))
        return Implies(a.r[35] == 7, And(even(a), odd_number(a)))

    for code in sorted(counts):
        if not expected[code]: continue
        label = f'bc77_odd_operand_word{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        if code in (1, 2, 3, 4): p.add(a.s1 == 4)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, invariant(b, dst))
            for dst in sorted(expected[code])]), f'ALL original{code:02X} preserves last25 operand invariant')
    print('PASS GLOBAL388 last25 cut: every native77 with selectorC/nonzeroR26 '
          'has EVEN type and ODD operandR29. OperandC is impossible. This '
          'closes the DIRECT high77/6D/60/48/B1/B3/BC-C writer for unlimited '
          'wait/key/serial timing, not only1D/R26eight. OddB operand/BB and '
          'other48/8B routes/later paths are NOT declared impossible.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    even_type_induction()
    all_nonzero_kind7_cut()
    high77_operand_cut()
    r['inlet']['immutable_reference']()
    print('PASS frozen reset/source/hash audit. No emulator/ROM repair, no new '
          'keyboard protocol, and no general impossibility claim for partialK2.', flush=True)
