#!/usr/bin/env python3
"""Complete counter3/4 C/E77 source cut: NUMBER stays zero before21.

The only external seeds are native06/07, not free high-type packets.
Original21 needs NUMBER>=5 to enter23 and the relevant25 resolver.
Its actual incoming number stays0. This closes these two counter cases
before any payload theorem, for ALL types, not only TYPEA.

Complete graph coverage is an overapproximation, never a key witness.
No ROM/reference/state/return edits, keyboard search or physical exchange.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, BitVecVal, If, Implies, Not, Or, UGE, unsat

root = Path(__file__).resolve().parent
arithmetic = runpy.run_path(str(root / 'cache-bc-counter67-arithmetic.py'))
higha = arithmetic['higha']
r, w, q, basis, states, edges, pred, execute = (arithmetic[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred', 'execute'))
A, B, eq, checked = (arithmetic[n] for n in ('A', 'B', 'eq', 'checked'))


def original21_gate():
    a = q['State']('counter34_exact21'); p = w['base'](a, 0x21)
    b = execute(a, p, 0x21, 'counter34_exact21')
    w['prove'](p, And(w['ip'](b) == If(UGE(a.r[29], 5), BitVecVal(0x23, 8),
                                    BitVecVal(0x22, 8)),
        b.r[29] == a.r[29], b.s == a.r[29]+11, b.s1 == 0,
        eq(A(b), A(a)), eq(B(b), B(a)),
        *[b.r[j] == a.r[j] for j in (26, 32, 35)]),
        'ORIGINAL21 selects23 iff incomingNUMBER>=5; no numeric payload change')


def complete_zero_number_cut():
    arithmetic['complete_graph']()
    checked('complete reset low07: selector!=8 has TYPE0 AND NUMBER0',
            higha['inlet']['low07_number_cut'])
    for counter, expected_size, expected_edges, ce_ids in (
            (3, 83, 97, {21640, 48387}), (4, 74, 85, {19863, 45872})):
        targets = {i for i, a in enumerate(states) if a[0] == 0x77
            and (a[7] is None or counter in a[7])
            and (a[5] is None or set(a[5]) & {12, 14})}
        assert targets == ce_ids
        region = basis['backward'](targets, {7, 0x1F, 0x1C})
        counts = Counter(states[i][0] for i in region)
        pairs = basis['internal_pairs'](region)
        assert len(region) == expected_size and sum(pairs.values()) == expected_edges
        assert set(counts) == {1, 2, 3, 4, 7, 0x18, 0x1B, 0x1D, 0x21, 0x23,
            0x24, 0x25, 0x26, 0x28, 0x60, 0x6D, 0x77, 0x7E, 0xBA, 0xCB,
            0xD4, 0xDD} | ({0x20, 0x2F} if counter == 3 else set())
        assert basis['external_pairs'](region) == {(6, 7): 6}
        assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
        assert all(states[i][3] == [4] for i in region if states[i][0] in (1, 2, 3, 4))
        assert Counter(states[j][0] for i in targets for j in pred[i]) == {0x7E: 2}
        all1d = {i for i, a in enumerate(states) if a[0] == 0x1D
                 and (a[7] is None or counter in a[7])}
        all25 = {i for i, a in enumerate(states) if a[0] == 0x25
                 and (a[7] is None or counter in a[7])}
        assert len(all1d) == 4 and all1d <= region
        assert all25 == {i for i in region if states[i][0] == 0x25}

        guard = lambda a: And(a.r[26] == counter, a.r[35] == 7)
        def inv(a, code):
            if code == 7: return Or(And(a.r[32] == 0, a.r[29] == 0), a.r[38] == 8)
            if code in (0x6D, 0x60):
                return Implies(And(guard(a), a.r[38] == 9), a.r[29] == 0)
            if code in (0x18, 0x1B):
                return Implies(guard(a), And(a.r[29] == 0, a.s1 == 0))
            if code in (0x1D, 0x20, 0x2F, 0x21):
                return Implies(guard(a), a.r[29] == 0)
            return Not(guard(a))

        for code in sorted(counts):
            label = f'counter34_complete{expected_size}_{code:02X}'
            a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
            if code in (1, 2, 3, 4): p.add(a.s1 == 4)
            b = execute(a, p, code, label)
            destinations = sorted({dst for first, dst in pairs if first == code})
            w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                               for dst in destinations]),
                f'ALL ORIGINAL{code:02X} preserves COMPLETE{expected_size}/{expected_edges} '
                f'counter{counter} zero-number/excluded-marker invariant')
        a = q['State'](f'counter34_final77_{counter}'); p = w['base'](a, 0x77)
        p.add(inv(a, 0x77), guard(a), Or(a.r[38] == 12, a.r[38] == 14))
        assert p.check() == unsat
        print(f'PASS GLOBAL counter{counter}/kind7 eligible C/E77 excluded for ALL types. '
              f'COMPLETE{expected_size}/{expected_edges}, ALL four1D/ALL25/BOTH77 '
              'contexts covered; real NUMBER0 cannot pass ORIGINAL21>=5 gate. '
              'Arbitrarily many20/2F/marker/type cycles do not open it.', flush=True)


def remaining_graph_counters():
    arithmetic['complete_graph']()
    targets = {i for i, a in enumerate(states) if a[0] == 0x77
        and (a[7] is None or any(v != 0 for v in a[7]))
        and (a[5] is None or set(a[5]) & {12, 14})}
    assert len(targets) == 24
    assert all(states[i][7] is not None for i in targets)
    domains = {v for i in targets for v in states[i][7] if v != 0}
    assert domains == {1, 2, 3, 4, 6, 7, 8, 15}
    assert all(states[i][0] == 0x7E for j in targets for i in pred[j])
    print('PASS COMPLETE C/E77 counter coverage:1/2/3/4/6/7/8/F only; '
          '5 and9..E absent. Joined with the proven3/4/6/7/8 exclusions, '
          'this audit alone leaves1/2/F (see the separate counterF cut). '
          'These are graph candidates, '
          'NOT positive native producers. Other BB/A3/CC/adapters are separate.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    original21_gate()
    complete_zero_number_cut()
    remaining_graph_counters()
    r['inlet']['immutable_reference']()
    print('PASS counter3/4 source cut. No general partialK2 impossibility, '
          'native/live/ALL5/key search or physical programme write claim.', flush=True)
