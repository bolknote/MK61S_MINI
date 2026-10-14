#!/usr/bin/env python3
"""Complete counterF/kind7 source exclusion and the remaining1/2 cases.

Native1F/1C seeds and the low07 source bound the TYPE before original2C
to an even tetra or1/3. Original2C swaps TYPE and KIND, so it cannot
preserve/produce KIND7 at counterF. All24 counterF25 and ten C/E77
contexts are covered, not just the low07 feedback loop.

The joined result narrows the two first-BB selectorC/E families to
counter1/2 candidates. It is a negative source theorem, NOT a native
key recipe, a useful Ms byte, a physical write/exchange, or a proof
that every BB/later adapter/partialK2 is impossible.

LATER AUDIT: cache-bc-counter12-source-cut.py closes BOTH remaining
1/2 cases and joins the first-BB family exclusion. The1/2 conclusion
below is the intermediate boundary of THIS older dependency, not a
current claim that either case is still an open native producer.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, Extract, Implies, Not, Or, unsat

root = Path(__file__).resolve().parent
number = runpy.run_path(str(root / 'cache-bc-counter34-number-cut.py'))
arithmetic, higha = number['arithmetic'], number['higha']
r, w, q, basis, states, edges, pred, execute = (number[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred', 'execute'))
checked, even = number['checked'], higha['even']


def complete_counterf_cut():
    arithmetic['complete_graph']()
    checked('complete reset low07 TYPE0 boundary outside selector8',
            higha['inlet']['low07_number_cut'])
    targets = {i for i, a in enumerate(states) if a[0] == 0x77
        and (a[7] is None or 15 in a[7])
        and (a[5] is None or set(a[5]) & {12, 14})}
    assert targets == {16319, 17037, 17847, 19714, 27605,
                       35176, 36757, 42930, 47257, 49550}
    region = basis['backward'](targets, {7, 0x1F, 0x1C})
    counts = Counter(states[i][0] for i in region)
    pairs = basis['internal_pairs'](region)
    assert len(region) == 637 and sum(pairs.values()) == 803
    assert counts == {1: 18, 2: 18, 3: 18, 4: 18, 7: 6, 0x18: 48,
        0x1A: 22, 0x1B: 48, 0x1C: 88, 0x1D: 48, 0x1F: 22,
        0x20: 8, 0x21: 8, 0x22: 8, 0x23: 8, 0x24: 8, 0x25: 24,
        0x26: 10, 0x28: 10, 0x2C: 25, 0x2D: 22, 0x2E: 24,
        0x2F: 16, 0x36: 8, 0x60: 4, 0x6D: 8, 0x77: 10,
        0x7E: 10, 0xBA: 18, 0xCB: 18, 0xD4: 10, 0xD6: 8, 0xDD: 18}
    assert basis['external_pairs'](region) == {
        (6, 7): 6, (0xA5, 0x1F): 30, (0x19, 0x1C): 44, (0x1E, 0x1C): 22}
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
    assert all(states[i][7] == [15] for i in region if states[i][0] in (0x1F, 0x1A))
    # BOTH resolver selector values occur; no S1=4 pin is imposed here.
    # The old exploratory4-only check is not coverage for these6 entries.
    assert {tuple(states[i][3]) for i in region if states[i][0] in (1, 2, 3, 4)} == {
        (4,), (6,)}
    all25 = {i for i, a in enumerate(states) if a[0] == 0x25
             and (a[7] is None or 15 in a[7])}
    assert len(all25) == 24 and all25 == {i for i in region if states[i][0] == 0x25}
    assert Counter(states[j][0] for i in targets for j in pred[i]) == {0x7E: 10}

    a = q['State']('counterF_exact2C'); p = w['base'](a, 0x2C)
    b = execute(a, p, 0x2C, 'counterF_exact2C')
    w['prove'](p, And(b.r[32] == a.r[35], b.r[35] == a.r[32],
                     b.r[26] == a.r[26]),
        'ORIGINAL2C swaps TYPE/KIND and holds counter; not a high-type-only producer')
    guard = lambda a: And(a.r[26] == 15, a.r[35] == 7)
    def inv(a, code):
        if code in (0x1F, 0x1C): return And()
        if code == 7: return Or(a.r[32] == 0, a.r[38] == 8)
        if code in (0x6D, 0x60): return Or(even(a), a.r[38] == 8)
        if code == 0x1A: return a.r[32] == 0
        if code == 0x18: return Or(even(a), And(a.r[26] == 15, a.r[32] == 1))
        if code == 0x1B: return Or(Extract(0, 0, a.r[32]) == 1,
            And(a.r[26] == 15, Or(a.r[32] == 0, a.r[32] == 2)))
        if code == 0x1D: return Or(even(a),
            And(a.r[26] == 15, Or(a.r[32] == 1, a.r[32] == 3)))
        if code == 0x2D: return a.r[32] == 2
        if code == 0x2C: return Or(even(a), a.r[32] == 1, a.r[32] == 3)
        if code == 0x77: return And(Not(guard(a)), even(a))
        return And(Not(guard(a)), Implies(a.r[35] == 7, even(a)))

    for code in sorted(counts):
        label = f'counterF_complete637_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        if code in (0x1F, 0x1A): p.add(a.r[26] == 15)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE637/803 counterF/kind correlation')
    a = q['State']('counterF_final77'); p = w['base'](a, 0x77)
    p.add(inv(a, 0x77), guard(a), Or(a.r[38] == 12, a.r[38] == 14))
    assert p.check() == unsat
    print('PASS GLOBAL counterF/kind7 at eligible C/E77 and ALL24 counterF25 '
          'excluded for ALL types. COMPLETE637/803 includes native1F/1C sources, '
          'both S1four/six resolver families, unlimited20/2F/marker cycles. '
          'Before2C TYPE is even or1/3, never7; the real swap destroys KIND7.', flush=True)


def joined_remaining_cases():
    # Recheck the negative source lemmas used by the joined conclusion.
    # No positive PRIMARY loop/state is replayed into a native calculator.
    checked('GLOBAL counter3/4 zero-number source exclusions', number['complete_zero_number_cut'])
    checked('GLOBAL counter6/7 TYPE/payload decimal exclusions', arithmetic['complete_decimal_source_cut'])
    checked('GLOBAL counter8 TYPE/payload fixed-eight exclusion', higha['complete_counter8_payload_lock'])
    checked('independent COMPLETE206/243 native68/65 source and four exits',
            higha['source']['native54']['sixtyfive']['complete68_source_induction'])
    number['remaining_graph_counters']()
    a = q['State']('counterF_joined7E'); p = w['base'](a, 0x7E)
    b = execute(a, p, 0x7E, 'counterF_joined7E')
    w['prove'](p, Implies(w['ip'](b) == 0x77, And(b.r[35] == 7,
        *[b.r[j] == a.r[j] for j in (26, 29, 32, 38)])),
        'ALL original7E->77 supplies KIND7, holds TYPE/NUMBER/counter/selector')
    print('PASS JOINED first-BB families77/C and68/E: the needed native '
          '77/TYPEA/C-E source can only use counter1/2. ALL other nonzero '
          'counter domains are absent or excluded. Neither remaining case '
          'is proved reachable/useful/safe; A3/CC/other writers/later adapters '
          'and partialK2 generally are NOT excluded.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    complete_counterf_cut()
    joined_remaining_cases()
    r['inlet']['immutable_reference']()
    print('PASS counterF and joined nonzero-counter source audit. Reference/ROM/112SG '
          'unchanged; no native/live/ALL5/key search or physical Ms exchange claim.', flush=True)
