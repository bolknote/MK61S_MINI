#!/usr/bin/env python3
"""Close the remaining counter1/2 sources of the first-BB C/E families.

Counter2 retains NUMBER0 through normalisation and the actual22/36/28
bypass; counter1 enters the S1six resolver at TYPE2, gets NUMBER3, then
imports an arbitrary full M1 word through D6. Neither can pass the real
21>=5 gate to23/25 and the required C/E77 inlet. COMPLETE96/116 and
101/119 cuts cover every native caller, not selected finite key paths.

Joined with the other nonzero-counter cuts this excludes the first-BB
77/C->60/48 and68/E->65/8B families. Other BB/A3/CC/48 sources, later
adapters and partialK2 generally are NOT excluded. All positive data
contracts are PRIMARY only; ring M1 is not assigned a physical Ms slot.
No reference/ROM/state/IP/return repair, native/live/key/ALL5 search.
"""
from collections import Counter
from pathlib import Path
import runpy

from z3 import And, BitVecVal, If, Implies, Not, Or, UGE, ULE, unsat

root = Path(__file__).resolve().parent
previous = runpy.run_path(str(root / 'cache-bc-counterf-kind-cut.py'))
arithmetic, higha = previous['arithmetic'], previous['higha']
r, w, q, basis, states, edges, pred, execute = (previous[n] for n in
    ('r', 'w', 'q', 'basis', 'states', 'edges', 'pred', 'execute'))
A, B, eq = (arithmetic[n] for n in ('A', 'B', 'eq'))
checked = previous['checked']


def original_data_words():
    for code in (0x20, 0x2F, 0xD6):
        label = f'counter12_data_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); out = []
        b = w['ex'](a, code, *q['arbitrary_keys'](label+'_keys'),
            serial_inputs=q['State'](label+'_serial').m, emitted_outputs=out)
        if code == 0x20:
            claim = And(w['ip'](b) == 0x2F, b.s == 6,
                eq(A(b)[:9], [*A(a)[1:9], A(a)[8]]))
        elif code == 0x2F:
            claim = And(w['ip'](b) == If(UGE(A(a)[9], 7), BitVecVal(0x21, 8),
                                       BitVecVal(0x20, 8)),
                b.s1 == a.r[26], eq(A(b), A(a)))
        else:
            claim = And(eq(A(b), a.m[:36:3]), b.s1 == a.r[35],
                        w['ip'](b) == w['stack'](a)[0])
        w['prove'](p, And(claim, eq(B(b), B(a)), eq(b.st[:36], a.st[:36]),
            eq(out, a.m), *[b.r[j] == a.r[j] for j in (2, 26, 29, 32, 35, 38)]),
            f'ORIGINAL{code:02X} exact normaliser/read contract; NUMBER held and no ring write')
        if code == 0x2F: continue
        # Arbitrarily vary the removed old A data, leaving independent
        # memories, other primary fields, keys and serial data identical.
        # This does not exclude an earlier copy or a re-read on other chips.
        other = q['State'](label+'_other'); paired = a.copy()
        for j in ([0] if code == 0x20 else range(0, 36, 3)):
            paired.r[j] = other.r[j]
        pins = q['arbitrary_keys'](label+'_pairkeys')
        serial = q['State'](label+'_pairserial').m; oa = []; ob = []
        aa = w['ex'](a, code, *pins, serial_inputs=serial, emitted_outputs=oa)
        bb = w['ex'](paired, code, *pins, serial_inputs=serial, emitted_outputs=ob)
        w['prove'](p, And(w['same'](aa, bb), eq(oa, ob)),
            f'ORIGINAL{code:02X} whole-primary/outgoing pair: oldA0 lost' if code == 0x20 else
            'ORIGINALD6 whole-primary/outgoing pair: ALL12 old A replaced, not parked')


def source_region(counter):
    arithmetic['complete_graph']()
    targets = {i for i, a in enumerate(states) if a[0] == 0x77
        and (a[7] is None or counter in a[7])
        and (a[5] is None or set(a[5]) & {12, 14})}
    assert targets == ({33690, 51720} if counter == 1 else {20909, 47513})
    region = basis['backward'](targets, {7, 0x1F, 0x1C})
    counts = Counter(states[i][0] for i in region)
    pairs = basis['internal_pairs'](region)
    expected = (101, 119) if counter == 1 else (96, 116)
    assert (len(region), sum(pairs.values())) == expected
    assert basis['external_pairs'](region) == {(6, 7): 7}
    assert not region & set(r['inlet']['g']['graph']['indexes']['roots'])
    assert Counter(states[j][0] for i in targets for j in pred[i]) == {0x7E: 2}
    all1d = {i for i, a in enumerate(states) if a[0] == 0x1D
             and (a[7] is None or counter in a[7])}
    all25 = {i for i, a in enumerate(states) if a[0] == 0x25
             and (a[7] is None or counter in a[7])}
    assert len(all1d) == (5 if counter == 1 else 4) and all1d <= region
    assert len(all25) == (4 if counter == 1 else 6)
    assert all25 == {i for i in region if states[i][0] == 0x25}
    assert set(counts) == {1, 2, 3, 4, 7, 0x18, 0x1B, 0x1D, 0x20, 0x21, 0x23,
        0x24, 0x25, 0x26, 0x28, 0x2F, 0x60, 0x6D, 0x77, 0x7E, 0xBA, 0xCB,
        0xD4, 0xDD} | ({0x2E, 0xD6} if counter == 1 else {0x22, 0x36})
    selectors = {tuple(states[i][3]) for i in region if states[i][0] in (1, 2, 3, 4)}
    assert selectors == ({(4,), (6,)} if counter == 1 else {(4,)})
    return counts, pairs


def check_transfers(counter, inv, counts, pairs):
    size, edge_count = (101, 119) if counter == 1 else (96, 116)
    for code in sorted(counts):
        label = f'counter12_complete{size}_{code:02X}'
        a = q['State'](label); p = w['base'](a, code); p.add(inv(a, code))
        # Counter1 has BOTH selector4 and selector6 contexts. Do not pin
        # it to4, or prove just a metadata-compatible selected path.
        if counter == 2 and code in (1, 2, 3, 4): p.add(a.s1 == 4)
        b = execute(a, p, code, label)
        destinations = sorted({dst for first, dst in pairs if first == code})
        w['prove'](p, And(*[Implies(w['ip'](b) == dst, inv(b, dst))
                           for dst in destinations]),
            f'ALL ORIGINAL{code:02X} preserves COMPLETE{size}/{edge_count} counter{counter} source invariant')
    a = q['State'](f'counter12_final77_{counter}'); p = w['base'](a, 0x77)
    p.add(inv(a, 0x77), a.r[26] == counter, a.r[35] == 7,
          Or(a.r[38] == 12, a.r[38] == 14))
    assert p.check() == unsat


def complete_counter2_cut():
    checked('native low07: selector!=8 has BOTH TYPE0 and NUMBER0',
            higha['inlet']['low07_number_cut'])
    counts, pairs = source_region(2)
    assert (0x36, 0x28) in pairs and (0x36, 0x25) not in pairs
    guard = lambda a: And(a.r[26] == 2, a.r[35] == 7)
    def inv(a, code):
        if code == 7: return Or(And(a.r[32] == 0, a.r[29] == 0), a.r[38] == 8)
        if code in (0x6D, 0x60):
            return Implies(And(guard(a), a.r[38] == 9), a.r[29] == 0)
        if code in (0x18, 0x1B):
            return Implies(guard(a), And(a.r[29] == 0, a.r[38] == 9, a.s1 == 0))
        if code in (0x1D, 0x2F, 0x20, 0x21, 0x22, 0x36, 0x28, 0x7E, 0x77):
            return Implies(guard(a), And(a.r[29] == 0, a.r[38] == 9))
        return Not(guard(a))
    check_transfers(2, inv, counts, pairs)
    print('PASS GLOBAL counter2/kind7 eligible C/E77 excluded for ALL types. '
          'COMPLETE96/116: ALL4 1D, ALL6 25, BOTH C/E77 included. '
          'Real22/36 bypass returns28, not25; TYPE may grow but NUMBER0 '
          'and selector9 persist. ANY20/2F loops cannot pass21>=5.', flush=True)


def complete_counter1_cut():
    checked('native low07 TYPE0/NUMBER0 boundary, independent of incoming M1 data',
            higha['inlet']['low07_number_cut'])
    counts, pairs = source_region(1)
    assert (0xDD, 0xD6) in pairs and (0xD6, 0x2F) in pairs
    assert (0x21, 0x23) in pairs and (0x21, 0x22) not in pairs
    guard = lambda a: And(a.r[26] == 1, a.r[35] == 7)
    def inv(a, code):
        if code == 7: return Or(And(a.r[32] == 0, a.r[29] == 0), a.r[38] == 8)
        if code in (0x6D, 0x60):
            return Implies(And(guard(a), a.r[38] == 9), a.r[32] == 0)
        if code == 0x18: return Implies(guard(a), And(a.r[32] == 0, a.s1 == 0))
        if code == 0x1B: return Implies(guard(a), And(a.r[32] == 1, a.s1 == 0))
        if code in (0x1D, 0x2E): return Implies(guard(a), a.r[32] == 2)
        if code == 1: return Implies(guard(a), And(a.r[32] == 2, a.s1 == 6))
        if code == 2:
            return Implies(guard(a), And(a.r[32] == 2, ULE(a.r[29], 2), a.s1 == 6))
        if code in (3, 4, 0xBA, 0xCB, 0xDD):
            return Implies(guard(a), And(a.r[32] == 2, a.r[29] == 3, a.s1 == 6))
        if code in (0xD6, 0x2F, 0x20, 0x21):
            return Implies(guard(a), And(a.r[32] == 2, a.r[29] == 3))
        return Not(guard(a))
    check_transfers(1, inv, counts, pairs)
    print('PASS GLOBAL counter1/kind7 eligible C/E77 excluded for ALL types. '
          'COMPLETE101/119: ALL5 1D, ALL4 25, BOTH C/E77, S1four/six covered. '
          'First resolver has TYPE2/NUMBER3; D6 imports ANY12 A tetras '
          'but holds TYPE/NUMBER. Real21 needs>=5, so highTYPE bootstrap '
          'cannot start; arbitrary marker/normaliser waits do not help.', flush=True)


def join_first_bb_exclusion():
    checked('GLOBAL counterF/kind7 exclusion including native1F/1C sources',
            previous['complete_counterf_cut'])
    checked('ALL other counter3/4/6/7/8 cuts and independent68 source; remaining1/2',
            previous['joined_remaining_cases'])
    checked('C-family exact first-BB TYPEA/NUMBERB requirement', higha['c_family_bb_type'])
    checked('E-family independent exact first-BB TYPEA/NUMBERB requirement', higha['e_family_bb_type'])
    print('PASS JOINED GLOBAL: BOTH first-BB families77/C->6D/60/48/B1/B3 '
          'and68/E->65/7B/B7/45/8B/48/B1/B3 are excluded natively. '
          'ALL nonzero-counter candidates covered; the earlier1/2 remainder '
          'is now closed. Other48/BB/A3/CC callers/later adapters/writers '
          'and partialK2 generally are NOT ruled out.', flush=True)


if __name__ == '__main__':
    r['inlet']['immutable_reference']()
    original_data_words()
    complete_counter2_cut()
    complete_counter1_cut()
    join_first_bb_exclusion()
    r['inlet']['immutable_reference']()
    print('PASS counter1/2 and joined first-BB source audit. No native/live/ALL5 '
          'key search, reference/ROM/state/IP/return repair or physical exchange claim.', flush=True)
