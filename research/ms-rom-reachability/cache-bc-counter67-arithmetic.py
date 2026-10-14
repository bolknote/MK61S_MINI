#!/usr/bin/env python3
"""Original23/24 arithmetic and the complete counter6/7 TYPEA cut.

Counter6 may modify A through23/24; counter7 always uses24. Thus the
fixed-eight invariant of counter8 is NOT reused. Instead each original
24 preserves the decimal domain of every individually decimal A tetra.
Four selector9 continuations seed a phased decimal-domain invariant.

The complete reset caller cuts join that payload invariant to ALL native
counter6/7 candidates, including unbounded wait/type-wrap cycles. Exact
word arithmetic retains four-bit operand masking, even for nondecimal
incoming tetras. No reference/ROM/state/IP/return repair, native keyboard
search, actual Ms identity or general partialK2 impossibility claim.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, BitVecVal, Extract, If, Implies, Or, UGE, ULE, ZeroExt, sat, unsat

root = Path(__file__).resolve().parent
higha = runpy.run_path(str(root / 'cache-bc-high-a-counter-audit.py'))
r, w, q, basis, states, edges, pred, execute, walk = (higha[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred', 'execute', 'walk'))
A, B, eq, checked = (higha[n] for n in ('A', 'B', 'eq', 'checked'))
even = higha['even']
decimal_controls = lambda a: And(*[ULE(A(a)[j], 9) for j in (0, 3, 6, 9)])


def complete_graph():
    graph = r['inlet']['g']['graph']
    assert len(states) == 52416 and sum(map(len, edges)) == 95731
    assert graph['metadata']['complete'] and graph['metadata']['pending'] == 0
    assert graph['metadata']['terminal'] is None
    assert graph['metadata']['fusedCommands'] == {'93': ['93', '94'], '12': ['12', 'C6']}
    assert all(states[i][0] == 0 for i in graph['indexes']['roots'])


def exact_arithmetic_words():
    for code in (0x1D, 0x23, 0x24):
        label = f'counter67_exact_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        if code == 0x24: p.add(Or(a.s == 6, a.s == 15))
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'),
            serial_inputs=q['State'](label+'_serial').m, emitted_outputs=out)
        held = And(eq(B(b), B(a)), eq(b.st[:36], a.st[:36]),
                   *[b.r[j] == a.r[j] for j in (2, 26, 29, 32, 35)])
        if code == 0x1D:
            claim = And(held, eq(A(b), A(a)), b.s == 15, b.s1 == 14,
                Implies(a.r[26] == 6, w['ip'](b) == 0x23),
                Implies(a.r[26] == 7, w['ip'](b) == 0x24))
        elif code == 0x23:
            claim = And(held, eq(A(b), A(a)), b.s == 6,
                w['ip'](b) == If(UGE(a.r[29], 8), BitVecVal(0x25, 8),
                                 BitVecVal(0x24, 8)))
        else:
            # Carry is from the five-bit binary sum. Every final result
            # is still a tetra; the internal +6 operands in later digits
            # are masked BEFORE their five-bit sum. Do not replace24 with
            # an ordinary unbounded integer/BCD adder for arbitrary A.
            total = ZeroExt(1, a.r[0])+ZeroExt(1, a.s)+1
            first = a.r[0]+a.s+1+If(UGE(total, 16), BitVecVal(0, 4), BitVecVal(10, 4))
            claim = And(held, eq(A(b)[9:], A(a)[9:]), b.s == 4, b.s1 == a.s1,
                w['ip'](b) == 0x25, b.r[0] == first,
                Implies(a.s == 6, ULE(b.r[0], 9)),
                Implies(a.s == 15, b.r[0] == a.r[0]),
                *[Implies(ULE(A(a)[j], 9), ULE(A(b)[j], 9)) for j in range(12)])
        w['prove'](p, And(claim, eq(out, a.m)),
            f'ORIGINAL{code:02X} exact gate/arithmetic/cache contract; no ring write')
    print('PASS original1D sets S=F/S1=E;23 selects24 iff oldNUMBER<8 '
          'and sets S=6. Original24: S6 normalizes A0 to0..9, SF holdsA0; '
          'every individually decimal digit stays decimal for either S. '
          'Other digits need not be decimal; A9..11/B12/ST12 are held.', flush=True)


def cache_body_lemmas():
    for code in (0x25, 1, 2, 3, 4, 0xBA, 0xCB):
        label = f'counter67_body_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        p.add(Or(a.r[26] == 6, a.r[26] == 7), a.r[35] == 7, even(a))
        if code != 0x25: p.add(a.s1 == 4)
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'),
            serial_inputs=q['State'](label+'_serial').m, emitted_outputs=out)
        w['prove'](p, And(eq(A(b), A(a)), eq(B(b), B(a)), eq(b.st[:36], a.st[:36]),
            eq(out, a.m), *[b.r[j] == a.r[j] for j in (2, 26, 32, 35)]),
            f'ORIGINAL{code:02X} counter6/7 payload/control held for any evenTYPE/oldMODE')


def original_cycle(a, p, counter, typ, label, *, complete=True):
    def step(before, code, index):
        w['prove'](p, w['ip'](before) == code, label+f' actual ORIGINAL{code:02X}', False)
        out = []
        after = w['ex'](before, code, *q['arbitrary_keys'](label+f'_keys{index}'),
            serial_inputs=q['State'](label+f'_serial{index}').m, emitted_outputs=out)
        return after, out

    prefix = [0x1D]
    if counter == 6: prefix.append(0x23)
    if counter == 7 or typ < 10: prefix.append(0x24)
    b = a
    for index, code in enumerate(prefix):
        before = b; b, out = step(b, code, index)
        w['prove'](p, eq(out, before.m), label+' arithmetic prefix does not write ring', False)
    numeric = b
    sequence = (0x25, 1, *([2]*(typ+1)), 3, 4, 0xBA, 0xCB,
                0xDD, 0xD4, 0x26, 0x28, 0x7E)
    for index, code in enumerate(sequence, len(prefix)):
        if code == 1: p.add(b.m[22] == 15)
        before = b; b, out = step(b, code, index)
        if code == 0xD4:
            w['prove'](p, And(eq(out[0:36:3], A(numeric)),
                *[out[j] == before.m[j] for j in range(42) if j % 3 != 0 or j >= 36]),
                label+' D4 writes POST-arithmetic A12, not an untouched entry backup', False)
        else: w['prove'](p, eq(out, before.m), label+' no other ring write', False)
    w['prove'](p, And(w['ip'](b) == 0x77, b.r[32] == typ, b.r[29] == typ+1,
        b.r[38] == A(numeric)[0]+1, b.r[26] == counter, b.r[35] == 7,
        eq(A(b), [*A(numeric)[2:], *A(numeric)[:2]]), eq(B(b), B(a))),
        label+' selector uses POST24 A0; original marker/counter/DD/26 rotation2')
    if not complete: return b
    p.add(b.r[38] == 9); assert p.check() == sat
    b = walk(b, p, (0x77, 0x6D, 0x60, 0x18, 0x1B), label+'_selector9_return')
    w['prove'](p, And(w['ip'](b) == 0x1D, b.r[32] == (typ+2) % 16,
        b.r[26] == counter, b.r[35] == 7, b.r[2] == 15,
        eq(A(b), [*A(numeric)[3:], *A(numeric)[:3]]), eq(B(b), B(a))),
        label+' selector9 grows TYPE by2 and rotates POST24 A by3')
    return b


def four_round_contracts():
    for counter in (6, 7):
        label = f'counter67_four_rounds_{counter}'
        a = q['State'](label); p = w['base'](a, 0x1D)
        p.add(a.r[32] == 2, a.r[35] == 7, a.r[26] == counter,
              a.r[29] == 0, a.r[25] == a.r[31])
        b = a
        for index, typ in enumerate((2, 4, 6, 8)):
            b = original_cycle(b, p, counter, typ, label+f'_{index}')
        w['prove'](p, And(w['ip'](b) == 0x1D, b.r[32] == 10, decimal_controls(b)),
            f'FOUR ORIGINAL counter{counter}/selector9 continuations seed ALL four decimal controls')
        b = original_cycle(b, p, counter, 10, label+'_TYPEA_final', complete=False)
        w['prove'](p, And(ULE(b.r[38], 10), b.r[38] != 12, b.r[38] != 14),
            f'TYPEA counter{counter}: fifth selector is1..A, NEVER C/E; fixed8 not assumed')
    print('PASS CONDITIONAL finite original-cycle compositions for both6/7. '
          'Arbitrary initial A is admitted; decimal-control locking replaces '
          'counter8 fixed-eight locking. Not native witnesses or key recipes.', flush=True)


def complete_decimal_source_cut():
    complete_graph()
    checked('complete reset low07/type0/number0 boundary outside selector8',
            higha['inlet']['low07_number_cut'])
    for counter, expected_size, expected_edges, ce_ids in (
            (6, 71, 82, {19042, 44177}), (7, 65, 73, {19057, 44256})):
        targets = {i for i, a in enumerate(states) if a[0] == 0x1D
                   and (a[7] is None or counter in a[7])}
        assert len(targets) == 4
        region = basis['backward'](targets, {7, 0x1F, 0x1C})
        counts = Counter(states[i][0] for i in region)
        pairs = basis['internal_pairs'](region)
        assert len(region) == expected_size and sum(pairs.values()) == expected_edges
        assert set(counts) == {1, 2, 3, 4, 7, 0x18, 0x1B, 0x1D, 0x24, 0x25,
            0x26, 0x28, 0x60, 0x6D, 0x77, 0x7E, 0xBA, 0xCB, 0xD4, 0xDD} | (
                {0x23} if counter == 6 else set())
        assert basis['external_pairs'](region) == {(6, 7): 6}
        assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
        assert all(states[i][3] == [4] for i in region if states[i][0] in (1, 2, 3, 4))
        ce = {i for i, a in enumerate(states) if a[0] == 0x77
            and (a[7] is None or counter in a[7])
            and (a[5] is None or set(a[5]) & {12, 14})}
        assert ce == ce_ids and ce <= region
        assert Counter(states[j][0] for i in ce for j in pred[i]) == {0x7E: 2}
        all25 = {i for i, a in enumerate(states) if a[0] == 0x25
                 and (a[7] is None or counter in a[7])}
        assert all25 == {i for i in region if states[i][0] == 0x25}

        guard = lambda a: And(a.r[26] == counter, a.r[35] == 7)
        def rule(a, typ, shift=0):
            positions = {4: (9,), 6: (6, 9), 8: (3, 6, 9),
                0: (0, 3, 6, 9), 10: (0, 3, 6, 9),
                12: (0, 3, 6, 9), 14: (0, 3, 6, 9)}
            return And(Extract(0, 0, typ) == 0,
                *[Implies(typ == value,
                    And(*[ULE(A(a)[(j-shift) % 12], 9) for j in indices]))
                  for value, indices in positions.items()])

        def inv(a, code):
            if code == 7: return Or(a.r[32] == 0, a.r[38] == 8)
            if code in (0x6D, 0x60):
                return Implies(And(guard(a), a.r[38] == 9), rule(a, a.r[32]+2, -1))
            if code == 0x18:
                return Implies(guard(a), And(a.r[38] == 9, rule(a, a.r[32]+2)))
            if code == 0x1B:
                return Implies(guard(a), And(a.r[38] == 9, rule(a, a.r[32]+1)))
            if code in (0xD4, 0x26):
                return Implies(guard(a), And(rule(a, a.r[32], 1), a.r[38] == A(a)[11]+1))
            if code in (0x28, 0x7E, 0x77):
                return Implies(guard(a), And(rule(a, a.r[32], 2), a.r[38] == A(a)[10]+1))
            packet = And(a.r[38] == 9, rule(a, a.r[32]))
            if code == 0x24: packet = And(packet, Or(a.s == 6, a.s == 15))
            return Implies(guard(a), packet)

        for code in sorted(counts):
            label = f'counter67_complete{expected_size}_{code:02X}'
            a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
            if code in (1, 2, 3, 4): p.add(a.s1 == 4)
            b = execute(a, p, code, label)
            destinations = sorted({dst for first, dst in pairs if first == code})
            w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                               for dst in destinations]),
                f'ALL ORIGINAL{code:02X} preserves COMPLETE{expected_size}/{expected_edges} '
                f'counter{counter} phased decimal invariant')
        a = q['State'](f'counter67_complete_CE_{counter}'); p = w['base'](a, 0x77)
        p.add(inv(a, 0x77), guard(a), a.r[32] == 10,
              Or(a.r[38] == 12, a.r[38] == 14))
        assert p.check() == unsat
        print(f'PASS GLOBAL counter{counter}/TYPEA/kind7: selectorC/E excluded. '
              f'COMPLETE{expected_size} classes/{expected_edges} edges, ALL four1D '
              'targets, ALL25 contexts and BOTH C/E77 candidates included. '
              'Unlimited01/02/7E waits and TYPE wrap covered; not only five rounds.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    exact_arithmetic_words()
    cache_body_lemmas()
    four_round_contracts()
    complete_decimal_source_cut()
    r['inlet']['immutable_reference']()
    print('PASS counter6/7 arithmetic/source audit. Other counters, other48/8B '
          'sources, A3/CC and partialK2 generally remain outside this exclusion. '
          'No native/live/ALL5/key search or physical memory exchange claim.', flush=True)
