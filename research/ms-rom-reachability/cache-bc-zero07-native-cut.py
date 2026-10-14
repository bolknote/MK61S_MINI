#!/usr/bin/env python3
"""Reset source cut for the two CONDITIONAL07/two-decoder writers.

No native keyboard/hardware experiment or reference mutation. The complete
reset graph supplies exhaustive caller coverage, NOT positive witnesses.
Exact ORIGINAL word contracts retain the missing vector/counter relation.
Both previously assumed07 inlets are the target, not all partialK2 paths.
"""
from collections import Counter, deque
from pathlib import Path
import runpy

from z3 import And, Implies, Not, Or, UGE, unsat

root = Path(__file__).resolve().parent
old = runpy.run_path(str(root / 'cache-bc-28-origin.py'))
r, w, q, states, edges, walk = (old[n] for n in
    ('r', 'w', 'q', 'states', 'edges', 'walk'))
pred = old['predecessors']()
wanted, origin = old['wanted'], old['origin']
high = lambda a: And(wanted(a), UGE(a.r[23], 3))
diagonal = lambda a: a.r[37] == a.r[40]
correlation = lambda a: And(diagonal(a), a.r[31] == 9, a.r[34] == a.r[40])
safe = lambda a: Implies(high(a), a.r[26] != 0)
before_increment = lambda a: And(a.r[31] == 9, Or(a.r[34] == 2, a.r[34] == 5))
dead_before = lambda a: And(a.r[31] == 0, Or(a.r[34] == 3, a.r[34] == 6))
dead_after = lambda a: And(a.r[31] == 7, Or(a.r[34] == 2, a.r[34] == 5))


def backward(targets, stops):
    region, todo = set(targets), deque(targets)
    while todo:
        i = todo.popleft()
        if states[i][0] in stops: continue
        for j in pred[i]:
            if j not in region: region.add(j); todo.append(j)
    return region


def internal_pairs(region):
    return Counter((states[i][0], states[j][0])
        for i in region for j in edges[i] if j in region)


def external_pairs(region):
    return Counter((states[i][0], states[j][0])
        for i, row in enumerate(edges) if i not in region for j in row if j in region)


def execute(a, p, code, label):
    """Expand BOTH original words in the two frozen graph fusions."""
    # This is a CONTROL/data-correlation proof, not a ring-preservation
    # contract. A3, E9 and other source words genuinely write memory.
    b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'))
    if code in (0x93, 0x12):
        second = 0x94 if code == 0x93 else 0xC6
        w['prove'](p, w['ip'](b) == second, label+' original fusion edge', False)
        b = w['ex'](b, second, *q['arbitrary_keys'](label+'_second_keys'))
    return b


def a3_diagonal_provenance():
    targets = {i for i, a in enumerate(states) if a[0] == 0xA3
               and any(states[j][0] == 0x55 for j in edges[i])}
    assert len(targets) == 1
    region = backward(targets, {0xA9})
    assert len(region) == 14
    counts = Counter(states[i][0] for i in region)
    assert counts == {0xA9: 2, 0x93: 2, 0x95: 1, 0x98: 1, 0x9A: 1,
        0xE5: 1, 0xE6: 1, 0xE9: 1, 0xAD: 2, 0xA2: 1, 0xA3: 1}
    pairs = internal_pairs(region)
    assert pairs == {(0xAD, 0xA2): 2, (0xAD, 0xA3): 2, (0xAD, 0xA9): 2,
        (0xAD, 0xAD): 2, (0x93, 0x95): 2, (0x95, 0x98): 1,
        (0x98, 0x9A): 1, (0x9A, 0xE5): 1, (0xE5, 0xE5): 1,
        (0xE5, 0xE6): 1, (0xE6, 0xE9): 1, (0xE9, 0xAD): 1,
        (0xA9, 0x93): 2, (0xA2, 0xA2): 1, (0xA2, 0xA3): 1}
    assert sum(pairs.values()) == 21
    assert external_pairs(region) == {(0xAD, 0xA9): 2}
    assert all(states[i][1][0] == 0x93 for i in region
               if states[i][0] in (0xA9, 0xAD))
    assert all(states[j][0] == 0xAD for i in region
               if states[i][0] == 0xA9 for j in pred[i])
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])

    # Every selected A9 is called by ORIGINAL AD, which establishes type9
    # and S1=9. Head93 is the complete graph's caller bound, not an edit.
    a = q['State']('zero07_A9_actual_caller'); p = w['base'](a, 0xAD)
    b = execute(a, p, 0xAD, 'zero07_A9_actual_caller')
    w['prove'](p, Implies(w['ip'](b) == 0xA9,
        And(b.r[32] == 9, b.s1 == 9, b.r[26] == 0)),
        'ALL ORIGINAL AD→A9 establishes type9/S1nine/counterzero')

    def invariant(a, code):
        if code == 0xA9:
            return And(a.r[32] == 9, a.s1 == 9, w['stack'](a)[0] == 0x93)
        if code == 0x93:
            return And(a.r[32] == 9, a.r[30] == 9, a.r[33] == a.r[35])
        if code in (0x95, 0x98, 0x9A):
            return And(a.r[32] == 9, diagonal(a), a.r[40] == a.r[35])
        return correlation(a)

    for code in sorted(counts):
        label = f'zero07_A3_provenance_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(invariant(a, code))
        if code == 0xAD: p.add(w['stack'](a)[0] == 0x93)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, invariant(b, dst))
                           for dst in destinations]),
            f'ALL original{code:02X} preserves COMPLETE14/21 A3 vector/counter relation')
    print('PASS GLOBAL selected A3 diagonal relation: vector vv implies '
          'B10/B11=v9. ALL14 classes/21 internal edges and unbounded '
          'AD/A2/E5 feedback covered; original93 AND94 expanded. '
          'Thus A3→22 carries29, A3→55 carries59, not a free byte.', flush=True)


def zero07_cut():
    targets = {i for i, a in enumerate(states) if a[0] == 7
        and (a[5] is None or set(a[5]) & {9, 10})
        and (a[7] is None or 0 in a[7])}
    assert len(targets) == 11
    region = backward(targets, {0x1F, 0x1C, 0xA3, 0x77})
    counts = Counter(states[i][0] for i in region)
    assert len(region) == 658 and len(counts) == 35 and counts == {
        1: 8, 2: 8, 3: 8, 4: 8, 6: 11, 7: 11, 0x12: 48,
        0x18: 52, 0x1A: 26, 0x1B: 52, 0x1C: 104, 0x1D: 52, 0x1F: 48,
        0x20: 8, 0x21: 8, 0x22: 9, 0x27: 26, 0x2E: 26, 0x2F: 16,
        0x36: 9, 0x37: 8, 0x38: 19, 0x3A: 7, 0x55: 1,
        0x61: 7, 0x62: 7, 0x6D: 8, 0x6E: 7, 0x6F: 7, 0x77: 16,
        0xA3: 1, 0xBA: 8, 0xCB: 8, 0xD6: 8, 0xDD: 8}
    pairs = internal_pairs(region)
    assert sum(pairs.values()) == 822
    assert external_pairs(region) == {(0xA5, 0x1F): 56, (0x19, 0x1C): 52,
        (0x1E, 0x1C): 26, (0xE7, 0x77): 6, (0xE9, 0x77): 3,
        (0xEE, 0x77): 6, (0xAD, 0xA3): 2, (0xA2, 0xA3): 1}
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
    assert {i for i in region if states[i][0] == 0xA3} == {
        i for i, a in enumerate(states) if a[0] == 0xA3
        and any(states[j][0] == 0x55 for j in edges[i])}
    # ONLY6F calls the seven62 nodes, and each62 has only6E in this cut.
    assert Counter(states[j][0] for i in region if states[i][0] == 0x62
                   for j in pred[i]) == {0x6F: 7}
    assert {dst for first, dst in pairs if first == 0x62} == {0x6E}
    print(f'PASS COMPLETE zero07 source/counter cut:658 classes/'
          f'{sum(pairs.values())} internal edges;11 targets; no root. '
          '6F/62 retained as actual two-word packet, not independent states.', flush=True)
    return region, counts, pairs


def onef_native_sources(region):
    entries = {i for i in region if states[i][0] == 0x1F}
    parents = {j for i in entries for j in pred[i]}
    assert Counter(states[j][0] for i in entries for j in pred[i]) == {0xA5: 56}
    assert Counter(states[k][0] for j in parents for k in pred[j]) == {0xAB: 66, 0xAD: 57}
    for code in (0xAB, 0xAD):
        label = f'zero07_1F_actual_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        b = execute(a, p, code, label); p.add(w['ip'](b) == 0xA5)
        b = walk(b, p, (0xA5,), label+'_A5')
        w['prove'](p, And(w['ip'](b) == 0x1F,
            Implies(wanted(b), And(b.r[26] == 15, UGE(b.s1, 7))),
            Implies(b.r[26] == 0, b.r[35] == 5)),
            f'ALL original{code:02X}/A5: wanted kinds require counterF/S1>=7; '
            'counterzero carries kind5')
    onecs = {i for i in region if states[i][0] == 0x1C}
    assert len(onecs) == 104 and all(states[i][7] == [0] for i in onecs)
    chain = backward(onecs, {0x1F})
    assert {states[i][0] for i in chain} == {0x1F, 0x17, 0x19, 0x1E, 0x1C}
    seed = {i for i in chain if states[i][0] == 0x1F}
    assert len(seed) == 26 and seed <= entries
    assert all(states[i][7] == [0] for i in seed)
    for code in (0x1F, 0x17, 0x19, 0x1E):
        label = f'zero07_1C_kind5_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(a.r[35] == 5, a.r[26] == 0)
        b = execute(a, p, code, label)
        w['prove'](p, And(b.r[35] == 5, b.r[26] == 0),
            f'ALL original{code:02X} preserves selected zero1C kind5/counterzero')
    print('PASS GLOBAL selected zero1F/1C sources: onlyAB/AD→A5, noD4 '
          'return family. Wanted9/B start with counterF AND S1>=7; '
          'they cannot take1F→12. Zero-counter1C has kind5, never9/B.', flush=True)


def zero_invariant(a, code):
    if code == 0x1F:
        return Implies(wanted(a), And(a.r[26] == 15, UGE(a.s1, 7)))
    # The selected native zero1C entries have kind5. Use the WEAKER
    # property in the word induction, so unconstrained nonzero1F→1C
    # transitions outside the graph slice cannot make it fail spuriously.
    if code == 0x1C: return safe(a)
    if code == 0x12: return Not(wanted(a))
    if code == 0xA3: return correlation(a)
    if code == 0x77: return And()
    if code in (0x22, 0x36, 0x37, 0x38, 0x55, 6):
        return Implies(high(a), Or(a.r[26] != 0, before_increment(a)))
    if code in (7, 0x6D):
        return Implies(high(a), Or(a.r[26] != 0, dead_before(a)))
    if code == 0x6F:
        return And(a.r[26] == 0, a.s1 == 14, Implies(high(a), dead_before(a)))
    if code == 0x6E: return Implies(high(a), dead_before(a))
    if code == 0x61: return Implies(high(a), dead_after(a))
    if code == 0x3A: return Not(high(a))
    return safe(a)


def native_zero07_induction():
    region, counts, pairs = zero07_cut()
    a3_diagonal_provenance()
    onef_native_sources(region)
    for code in sorted(counts):
        if code == 0x62 or not counts[code]: continue
        label = f'zero07_native_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(zero_invariant(a, code))
        b = execute(a, p, code, label)
        if code == 0x6F:
            w['prove'](p, w['ip'](b) == 0x62, 'ORIGINAL6F forces62', False)
            b = execute(b, p, 0x62, label+'_62')
            destinations = [0x6E]
        else: destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, zero_invariant(b, dst))
                           for dst in destinations]),
            f'ALL original{code:02X} preserves COMPLETE zero07 native joint invariant')
    print('PASS GLOBAL zero07/selector9/A: wanted9/B + flag>=3 + counterzero '
          'requires B10=0 AND B11=3/6 (bytes30/60). ORIGINAL6F/62/6E '
          'makes27/57;61 must exit63, never3A. The previously CONDITIONAL '
          '38-byte three-pass preparer has NO native source in this cut.', flush=True)
    for kind, mode, pointer in ((9, 15, 9), (11, 7, 10)):
        label = f'zero07_native_preparer_excluded_kind{kind:X}'
        a = q['State'](label); p = w['base'](a, 7)
        p.add(zero_invariant(a, 7), a.r[35] == kind, a.r[2] == mode,
              a.r[38] == pointer, a.r[26] == 0, UGE(a.r[23], 3))
        # Nonempty PRIMARY necessity premise, not a native positive run.
        w['prove'](p, Not(Or(*[w['byte'](a.r[31], a.r[34]) == value
                              for value in old['ALLOWED_BYTES']])),
            f'ALL native-shaped zero07/kind{kind:X} excludes all38 preparer bytes')
    a = q['State']('zero07_dead_counter_61'); p = w['base'](a, 0x61)
    p.add(dead_after(a)); b = execute(a, p, 0x61, 'zero07_dead_counter_61')
    w['prove'](p, w['ip'](b) == 0x63,
        'ORIGINAL61 with27/57 MUST exit63, not only fail the3A guard')
    return region


def native_nonzero07_cut(zero_region):
    region, counts, pairs = old['source_cut']()
    assert {i for i in region if states[i][0] == 0x6E} == {
        i for i in zero_region if states[i][0] == 0x6E}
    old['all_1c_selector_provenance']()
    for code in sorted(counts):
        label = f'nonzero07_native_induction_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        def invariant(s, word):
            if word == 0x6E: return Or(origin(s), dead_before(s))
            if word == 0x61: return Or(origin(s), dead_after(s))
            return old['origin_invariant'](s, word)
        p.add(invariant(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, invariant(b, dst))
                           for dst in destinations]),
            f'ALL original{code:02X} preserves COMPLETE nonzero07 native source invariant')
    print('PASS GLOBAL nonzero07/selector9/A: kinds9/B + flag>=3 require '
          'selector=kind+8 (1/3), NOT9/A. BOTH earlier07/two-decoder '
          'writer profiles are excluded from reset, not merely unbuilt. '
          'Other28/7A/7C/BB sources and partialK2 generally are NOT excluded.', flush=True)
    for kind, mode, pointer in ((9, 15, 9), (11, 7, 10)):
        a = q['State'](f'nonzero07_joint_excluded_kind{kind:X}'); p = w['base'](a, 7)
        p.add(old['origin_invariant'](a, 7), a.r[35] == kind, a.r[2] == mode,
              a.r[38] == pointer, a.r[26] != 0, UGE(a.r[23], 3))
        assert p.check() == unsat
    print('PASS BOTH native joint07 writer packets UNSAT under proved '
          'reset source invariant. No full/partialK2 global prohibition.', flush=True)


def native_first28_flag_cut():
    """Lift the07 source theorem to ALL53 initial28 candidates."""
    counts, pairs = old['inlet']['source_cut']()
    targets = {i for i, a in enumerate(states) if a[0] == 0x28
        and (a[7] is None or any(v != 0 for v in a[7]))}
    region = backward(targets, {7, 0x1F, 0x1C})
    native07 = {i for i, a in enumerate(states) if a[0] == 7
        and (a[5] is None or set(a[5]) & {9, 10})
        and (a[7] is None or any(v != 0 for v in a[7]))}
    assert {i for i in region if states[i][0] == 7} == native07
    assert len(region) == 1213 and len(counts) == 33
    for code in sorted(counts):
        label = f'first28_native_flag_{code:02X}'
        a = q['State'](label); p = w['base'](a, code)
        p.add(old['origin_invariant'](a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, old['origin_invariant'](b, dst))
                           for dst in destinations]),
            f'ALL original{code:02X} preserves COMPLETE first28 native flag cut')
    for kind in (9, 11):
        label = f'first28_native_low_flag_kind{kind:X}'
        a = q['State'](label); p = w['base'](a, 0x28)
        p.add(a.r[26] != 0, a.r[35] == kind, old['origin_invariant'](a, 0x28))
        prefix = ((0x28, 0x7E, 0x79, 0x45, 0x8B) if kind == 9 else
                  (0x28, 0x7E, 0x7B, 0xB7, 0x45, 0x8B))
        b = walk(a, p, prefix, label)
        w['prove'](p, And(w['ip'](b) == 0x48, b.r[23] == a.r[23], Not(UGE(b.r[23], 3))),
            f'ALL initial28/kind{kind:X} first48 flag<=2, not the54 gate flag>=3')
    print('PASS GLOBAL ALL53 initial nonzero28: kinds9/B imply R23<=2; '
          'first79/7B decoder cannot use the flag>=3 TWO-decoder54 bridge. '
          'ALL four28 parent families covered. Later7A/7C, BB, other48 '
          'sources and partialK2 generally remain OPEN.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    zero_region = native_zero07_induction()
    native_nonzero07_cut(zero_region)
    native_first28_flag_cut()
    r['inlet']['immutable_reference']()
    print('PASS source-driven native inlet exclusion. No key search, native '
          'capture, live hardware, ROM/state/return repair or global '
          'partialK2 impossibility claim.', flush=True)
